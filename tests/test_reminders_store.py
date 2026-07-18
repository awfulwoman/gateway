from __future__ import annotations
import pytest
import gateway.reminders.store as store
from gateway.config import RemindersConfig


@pytest.fixture
def db(tmp_path):
    store.init(RemindersConfig(db_path=str(tmp_path / "reminders.db")))
    return store


def make(id=None, title="Buy milk", updated_at="2026-07-18T09:00:00Z", **kw):
    id = id or store.new_id()
    r = {
        "id": id,
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


def test_upsert_then_get_round_trips(db):
    r = make(title="Buy compost")
    stored = db.upsert(r)
    assert stored["title"] == "Buy compost"
    assert db.get(r["id"]) == stored


def test_get_missing_returns_none(db):
    assert db.get("nonexistent") is None


def test_upsert_rejects_empty_title(db):
    r = make(title="")
    with pytest.raises(ValueError):
        db.upsert(r)


def test_upsert_requires_lat_lon_when_location_present(db):
    r = make(location={"name": "Tesco", "lat": None, "lon": None, "radius_m": 150, "trigger": "arrive"})
    with pytest.raises(ValueError):
        db.upsert(r)


def test_location_round_trips(db):
    loc = {"name": "Späti", "lat": 52.52, "lon": 13.405, "radius_m": 150, "trigger": "arrive"}
    r = make(location=loc)
    stored = db.upsert(r)
    assert stored["location"] == loc


def test_location_none_round_trips(db):
    r = make(location=None)
    stored = db.upsert(r)
    assert stored["location"] is None


def test_incoming_newer_update_replaces_local(db):
    r1 = make(updated_at="2026-07-18T09:00:00Z", title="First")
    db.upsert(r1)
    r2 = make(id=r1["id"], updated_at="2026-07-18T09:05:00Z", title="Second")
    stored = db.upsert(r2)
    assert stored["title"] == "Second"


def test_incoming_older_update_is_rejected(db):
    r1 = make(updated_at="2026-07-18T09:05:00Z", title="Newer")
    db.upsert(r1)
    r2 = make(id=r1["id"], updated_at="2026-07-18T09:00:00Z", title="Older")
    with pytest.raises(store.Stale) as exc:
        db.upsert(r2)
    assert exc.value.current["title"] == "Newer"
    assert db.get(r1["id"])["title"] == "Newer"


def test_incoming_equal_update_is_a_noop_rejection(db):
    r1 = make(updated_at="2026-07-18T09:00:00Z", title="First")
    db.upsert(r1)
    r2 = make(id=r1["id"], updated_at="2026-07-18T09:00:00Z", title="Second")
    with pytest.raises(store.Stale):
        db.upsert(r2)
    assert db.get(r1["id"])["title"] == "First"


def test_soft_delete_writes_tombstone(db):
    r = make()
    db.upsert(r)
    tombstone = db.soft_delete(r["id"])
    assert tombstone["deleted"] is True
    assert db.get(r["id"])["deleted"] is True


def test_soft_delete_missing_raises(db):
    with pytest.raises(KeyError):
        db.soft_delete("nonexistent")


def test_later_edit_resurrects_earlier_tombstone(db):
    r = make(updated_at="2026-07-18T09:00:00Z")
    db.upsert(r)
    db.soft_delete(r["id"], updated_at="2026-07-18T09:05:00Z")
    resurrected = make(id=r["id"], updated_at="2026-07-18T09:10:00Z", deleted=False)
    stored = db.upsert(resurrected)
    assert stored["deleted"] is False


def test_later_delete_buries_earlier_edit(db):
    r = make(updated_at="2026-07-18T09:00:00Z")
    db.upsert(r)
    edit = make(id=r["id"], updated_at="2026-07-18T09:05:00Z", title="Edited")
    db.upsert(edit)
    db.soft_delete(r["id"], updated_at="2026-07-18T09:10:00Z")
    assert db.get(r["id"])["deleted"] is True


def test_list_reminders_since_filter(db):
    r1 = make(updated_at="2026-07-18T09:00:00Z")
    r2 = make(updated_at="2026-07-18T09:10:00Z")
    db.upsert(r1)
    db.upsert(r2)
    results = db.list_reminders(since="2026-07-18T09:05:00Z")
    assert [r["id"] for r in results] == [r2["id"]]


def test_list_reminders_since_includes_tombstones(db):
    r = make(updated_at="2026-07-18T09:00:00Z")
    db.upsert(r)
    db.soft_delete(r["id"], updated_at="2026-07-18T09:10:00Z")
    results = db.list_reminders(since="2026-07-18T09:05:00Z")
    assert len(results) == 1
    assert results[0]["deleted"] is True


def test_list_reminders_include_deleted_false_excludes_tombstones(db):
    r = make()
    db.upsert(r)
    db.soft_delete(r["id"])
    assert db.list_reminders(include_deleted=False) == []


def test_list_reminders_filters_by_list_name(db):
    db.upsert(make(list="Shopping"))
    db.upsert(make(list="Reminders"))
    results = db.list_reminders(list_name="Shopping")
    assert len(results) == 1
    assert results[0]["list"] == "Shopping"


def test_unknown_keys_round_trip_through_extra(db):
    r = make(parent_id="parent-uuid-123", rrule="FREQ=DAILY", made_up_field=42)
    stored = db.upsert(r)
    assert stored["parent_id"] == "parent-uuid-123"
    assert stored["rrule"] == "FREQ=DAILY"
    assert stored["made_up_field"] == 42

    fetched = db.get(r["id"])
    assert fetched["parent_id"] == "parent-uuid-123"
    assert fetched["rrule"] == "FREQ=DAILY"
    assert fetched["made_up_field"] == 42


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


def test_gc_tombstones_leaves_non_deleted_rows(db):
    old_ts = "2020-01-01T00:00:00Z"
    r = make(updated_at=old_ts)
    db.upsert(r)
    removed = db.gc_tombstones(older_than_days=30)
    assert removed == 0
    assert db.get(r["id"]) is not None
