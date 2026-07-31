from __future__ import annotations
import pytest
import gateway.calendar_server.store as store
from gateway.config import CalendarServerConfig


@pytest.fixture
def db(calendar_server, calendar_server_token):
    store.init(CalendarServerConfig(base_url=calendar_server, bearer_token=calendar_server_token))
    return store


def make(id=None, title="Standup", start="2026-07-18T09:00:00Z", end="2026-07-18T09:30:00Z", updated_at="2026-07-18T09:00:00Z", **kw):
    id = id or store.new_id()
    e = {
        "id": id,
        "title": title,
        "notes": None,
        "location": None,
        "all_day": False,
        "start": start,
        "end": end,
        "calendar": "Calendar",
        "url": None,
        "created_at": updated_at,
        "updated_at": updated_at,
        "deleted": False,
    }
    e.update(kw)
    return e


def test_upsert_then_get_round_trips(db):
    e = make(title="Dentist")
    stored = db.upsert(e)
    assert stored["title"] == "Dentist"
    assert db.get(e["id"]) == stored


def test_get_missing_returns_none(db):
    assert db.get("nonexistent") is None


def test_upsert_rejects_empty_title(db):
    e = make(title="")
    with pytest.raises(ValueError):
        db.upsert(e)


def test_upsert_rejects_missing_start(db):
    e = make(start=None)
    with pytest.raises(ValueError):
        db.upsert(e)


def test_upsert_rejects_end_before_start(db):
    e = make(start="2026-07-18T10:00:00Z", end="2026-07-18T09:00:00Z")
    with pytest.raises(ValueError):
        db.upsert(e)


def test_incoming_newer_update_replaces_local(db):
    e1 = make(updated_at="2026-07-18T09:00:00Z", title="First")
    db.upsert(e1)
    e2 = make(id=e1["id"], updated_at="2026-07-18T09:05:00Z", title="Second")
    stored = db.upsert(e2)
    assert stored["title"] == "Second"


def test_incoming_older_update_is_rejected(db):
    e1 = make(updated_at="2026-07-18T09:05:00Z", title="Newer")
    db.upsert(e1)
    e2 = make(id=e1["id"], updated_at="2026-07-18T09:00:00Z", title="Older")
    with pytest.raises(store.Stale) as exc:
        db.upsert(e2)
    assert exc.value.current["title"] == "Newer"
    assert db.get(e1["id"])["title"] == "Newer"


def test_soft_delete_writes_tombstone(db):
    e = make()
    db.upsert(e)
    tombstone = db.soft_delete(e["id"])
    assert tombstone["deleted"] is True
    assert db.get(e["id"])["deleted"] is True


def test_soft_delete_missing_raises(db):
    with pytest.raises(KeyError):
        db.soft_delete("nonexistent")


def test_list_events_since_filter(db):
    e1 = make(updated_at="2026-07-18T09:00:00Z")
    e2 = make(updated_at="2026-07-18T09:10:00Z")
    db.upsert(e1)
    db.upsert(e2)
    results = db.list_events(since="2026-07-18T09:05:00Z")
    assert [e["id"] for e in results] == [e2["id"]]


def test_list_events_include_deleted_false_excludes_tombstones(db):
    e = make()
    db.upsert(e)
    db.soft_delete(e["id"])
    assert db.list_events(include_deleted=False) == []


def test_list_events_filters_by_calendar(db):
    db.upsert(make(calendar="Work"))
    db.upsert(make(calendar="Home"))
    results = db.list_events(calendar_name="Work")
    assert len(results) == 1
    assert results[0]["calendar"] == "Work"


def test_list_calendars(db):
    db.upsert(make(calendar="Work"))
    db.upsert(make(calendar="Home"))
    assert sorted(db.list_calendars()) == ["Home", "Work"]


def test_gc_tombstones_removes_old_deletes_only(db):
    old_ts = "2020-01-01T00:00:00Z"
    old_delete_ts = "2020-01-01T00:00:01Z"
    recent_ts = store.now_utc()

    old = make(updated_at=old_ts)
    db.upsert(old)
    db.soft_delete(old["id"], updated_at=old_delete_ts)

    recent = make(updated_at=recent_ts)
    db.upsert(recent)
    db.soft_delete(recent["id"], updated_at="9999-01-01T00:00:00Z")

    removed = db.gc_tombstones(older_than_days=30)
    assert removed == 1
    assert db.get(old["id"]) is None
    assert db.get(recent["id"]) is not None
