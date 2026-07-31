from __future__ import annotations
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
import gateway.reminders.geocode as geocode
import gateway.reminders.http as reminders_http
import gateway.reminders.store as store
from gateway.config import RemindersConfig, RemindersServerConfig

AUTH = {"Authorization": "Bearer good-token"}


@pytest.fixture
def client(reminders_server, reminders_server_token):
    config = RemindersConfig(
        api_tokens=["good-token"],
        nominatim_url="https://nominatim.example.com",
    )
    store.init(RemindersServerConfig(base_url=reminders_server, bearer_token=reminders_server_token))
    geocode.init(config)
    reminders_http.init(config)
    app = Starlette(routes=reminders_http.routes)
    return TestClient(app)


def make(id=None, title="Buy milk", updated_at="2026-07-18T09:00:00Z", **kw):
    r = {
        "id": id or store.new_id(),
        "title": title,
        "notes": None,
        "due": None,
        "priority": 0,
        "list": "Reminders",
        "done": False,
        "completed_at": None,
        "location": None,
        "created_at": updated_at,
        "updated_at": updated_at,
        "deleted": False,
    }
    r.update(kw)
    return r


def test_get_reminders_requires_auth(client):
    r = client.get("/v1/reminders")
    assert r.status_code == 401


def test_get_reminders_rejects_bad_token(client):
    r = client.get("/v1/reminders", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_get_reminders_empty(client):
    r = client.get("/v1/reminders", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["reminders"] == []
    assert "server_time" in body


def test_put_then_get_round_trips(client):
    reminder = make(title="Buy compost")
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["title"] == "Buy compost"

    r = client.get("/v1/reminders", headers=AUTH)
    assert len(r.json()["reminders"]) == 1


def test_put_forces_id_from_path(client):
    reminder = make(id="wrong-id", title="Buy compost")
    path_id = store.new_id()
    r = client.put(f"/v1/reminders/{path_id}", json=reminder, headers=AUTH)
    assert r.json()["id"] == path_id


def test_put_round_trips_unknown_fields(client):
    reminder = make(parent_id="parent-uuid-123", rrule="FREQ=DAILY")
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.json()["parent_id"] == "parent-uuid-123"
    assert r.json()["rrule"] == "FREQ=DAILY"

    r = client.get("/v1/reminders", headers=AUTH)
    fetched = r.json()["reminders"][0]
    assert fetched["parent_id"] == "parent-uuid-123"
    assert fetched["rrule"] == "FREQ=DAILY"


def test_put_stale_write_returns_409_with_current(client):
    reminder = make(updated_at="2026-07-18T09:05:00Z", title="Newer")
    client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)

    stale = make(id=reminder["id"], updated_at="2026-07-18T09:00:00Z", title="Older")
    r = client.put(f"/v1/reminders/{reminder['id']}", json=stale, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["current"]["title"] == "Newer"


def test_put_rejects_empty_title(client):
    reminder = make(title="")
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.status_code == 400


def test_put_resolves_location_name_via_geocode(client, monkeypatch):
    monkeypatch.setattr(geocode, "forward", lambda q: {"name": "Tesco", "lat": 51.5, "lon": -0.1})
    reminder = make(location={"name": "Tesco", "lat": None, "lon": None, "radius_m": 150, "trigger": "arrive"})
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["location"]["lat"] == 51.5


def test_put_400_on_unresolvable_location(client, monkeypatch):
    monkeypatch.setattr(geocode, "forward", lambda q: None)
    reminder = make(location={"name": "Nowhereville", "lat": None, "lon": None, "radius_m": 150, "trigger": "arrive"})
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.status_code == 400


def test_put_skips_geocode_when_coords_already_present(client, monkeypatch):
    called = []
    monkeypatch.setattr(geocode, "forward", lambda q: called.append(q))
    reminder = make(location={"name": "Somewhere", "lat": 1.0, "lon": 2.0, "radius_m": 150, "trigger": "arrive"})
    r = client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    assert r.status_code == 200
    assert called == []


def test_delete_reminder(client):
    reminder = make()
    client.put(f"/v1/reminders/{reminder['id']}", json=reminder, headers=AUTH)
    r = client.delete(f"/v1/reminders/{reminder['id']}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_delete_unknown_returns_404(client):
    r = client.delete(f"/v1/reminders/{store.new_id()}", headers=AUTH)
    assert r.status_code == 404


def test_sync_batch_mixed_accept_and_reject(client):
    existing = make(updated_at="2026-07-18T09:05:00Z", title="Newer")
    client.put(f"/v1/reminders/{existing['id']}", json=existing, headers=AUTH)

    accepted_change = make(title="New task")
    stale_change = make(id=existing["id"], updated_at="2026-07-18T09:00:00Z", title="Stale edit")

    r = client.post(
        "/v1/reminders/sync",
        json={"since": None, "changes": [accepted_change, stale_change]},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["id"] == existing["id"]
    assert body["rejected"][0]["current"]["title"] == "Newer"
    ids_in_response = {rem["id"] for rem in body["reminders"]}
    assert accepted_change["id"] in ids_in_response
    assert existing["id"] in ids_in_response


def test_sync_since_null_returns_full_snapshot(client):
    client.put(f"/v1/reminders/{make()['id']}", json=make(), headers=AUTH)
    r = client.post("/v1/reminders/sync", json={"since": None, "changes": []}, headers=AUTH)
    assert len(r.json()["reminders"]) == 1


def test_sync_since_continuity(client):
    r1 = client.get("/v1/reminders", headers=AUTH)
    server_time = r1.json()["server_time"]

    reminder = make(updated_at=store.now_after(server_time))
    r2 = client.post("/v1/reminders/sync", json={"since": server_time, "changes": [reminder]}, headers=AUTH)
    body = r2.json()
    assert [x["id"] for x in body["reminders"]] == [reminder["id"]]


def test_sync_requires_auth(client):
    r = client.post("/v1/reminders/sync", json={"since": None, "changes": []})
    assert r.status_code == 401


def test_geocode_forward(client, monkeypatch):
    monkeypatch.setattr(geocode, "forward", lambda q: {"name": "Späti", "lat": 52.52, "lon": 13.405})
    r = client.get("/v1/geocode", params={"q": "Späti"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"name": "Späti", "lat": 52.52, "lon": 13.405}


def test_geocode_reverse(client, monkeypatch):
    monkeypatch.setattr(geocode, "reverse", lambda lat, lon: {"name": "Boxhagener Platz", "lat": lat, "lon": lon})
    r = client.get("/v1/geocode", params={"lat": "52.5", "lon": "13.4"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "Boxhagener Platz"


def test_geocode_404_on_no_match(client, monkeypatch):
    monkeypatch.setattr(geocode, "forward", lambda q: None)
    r = client.get("/v1/geocode", params={"q": "nowhere"}, headers=AUTH)
    assert r.status_code == 404


def test_geocode_requires_q_or_latlon(client):
    r = client.get("/v1/geocode", headers=AUTH)
    assert r.status_code == 400


def test_geocode_requires_auth(client):
    r = client.get("/v1/geocode", params={"q": "Späti"})
    assert r.status_code == 401
