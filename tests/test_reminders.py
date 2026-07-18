from __future__ import annotations
import json
import pytest
import gateway.tools.reminders as reminders
from gateway.config import RemindersConfig


@pytest.fixture
def rem(tmp_path):
    reminders.init(RemindersConfig(db_path=str(tmp_path / "reminders.db")))
    return reminders


def test_list_reminder_lists_empty(rem):
    assert json.loads(rem.list_reminder_lists()) == []


def test_create_reminder_defaults_to_reminders_list(rem):
    result = json.loads(rem.create_reminder("Buy milk"))
    assert result["title"] == "Buy milk"
    assert result["list"] == "Reminders"

    lists = json.loads(rem.list_reminder_lists())
    assert lists == [{"name": "Reminders"}]


def test_create_reminder_in_named_list(rem):
    rem.create_reminder("Buy milk", list_name="Shopping", priority=1)
    items = json.loads(rem.list_reminders())
    assert len(items) == 1
    assert items[0]["title"] == "Buy milk"
    assert items[0]["list"] == "Shopping"
    assert items[0]["priority"] == 1
    assert items[0]["done"] is False


def test_create_reminder_with_due_and_notes(rem):
    rem.create_reminder("Pay rent", due_iso="2026-08-01", notes="via bank transfer", list_name="Bills")
    items = json.loads(rem.list_reminders(list_name="Bills"))
    assert items[0]["due"] == "2026-08-01"
    assert items[0]["notes"] == "via bank transfer"


def test_list_reminders_filters_by_missing_list(rem):
    rem.create_reminder("Buy milk", list_name="Shopping")
    assert json.loads(rem.list_reminders(list_name="Nonexistent")) == []


def test_create_reminder_rejects_empty_title(rem):
    result = json.loads(rem.create_reminder(""))
    assert "error" in result
    assert json.loads(rem.list_reminders()) == []


def test_create_reminder_with_location_resolves_via_geocode(rem, monkeypatch):
    monkeypatch.setattr(reminders.geocode, "forward", lambda q: {"name": "Tesco Express", "lat": 51.5, "lon": -0.1})
    result = json.loads(rem.create_reminder("Buy eggs", location_name="Tesco", arrive_or_leave="arrive"))
    assert result["location"] == {
        "name": "Tesco Express", "lat": 51.5, "lon": -0.1, "radius_m": 150, "trigger": "arrive",
    }


def test_create_reminder_with_custom_radius(rem, monkeypatch):
    monkeypatch.setattr(reminders.geocode, "forward", lambda q: {"name": "Tesco Express", "lat": 51.5, "lon": -0.1})
    result = json.loads(rem.create_reminder("Buy eggs", location_name="Tesco", radius_m=300))
    assert result["location"]["radius_m"] == 300


def test_create_reminder_with_unresolvable_location_errors(rem, monkeypatch):
    monkeypatch.setattr(reminders.geocode, "forward", lambda q: None)
    result = json.loads(rem.create_reminder("Buy eggs", location_name="Nowhereville"))
    assert "error" in result
    assert json.loads(rem.list_reminders()) == []


def test_complete_reminder(rem):
    rem.create_reminder("Walk dog")
    result = json.loads(rem.complete_reminder("walk"))
    assert result["title"] == "Walk dog"
    assert result["done"] is True
    assert result["completed_at"] is not None

    assert json.loads(rem.list_reminders()) == []
    completed = json.loads(rem.list_reminders(include_completed=True))
    assert completed[0]["done"] is True


def test_complete_reminder_not_found(rem):
    result = json.loads(rem.complete_reminder("nonexistent"))
    assert result == {"status": "not_found", "message": "No incomplete reminder matching: nonexistent"}


def test_delete_reminder(rem):
    rem.create_reminder("Old task")
    result = json.loads(rem.delete_reminder("old"))
    assert result["title"] == "Old task"
    assert result["deleted"] is True
    assert json.loads(rem.list_reminders(include_completed=True)) == []


def test_delete_reminder_not_found(rem):
    result = json.loads(rem.delete_reminder("nonexistent"))
    assert result == {"status": "not_found", "message": "No reminder matching: nonexistent"}


def test_search_reminders_matches_title_and_notes(rem):
    rem.create_reminder("Call dentist", notes="reschedule appointment")
    rem.create_reminder("Buy stamps")

    by_title = json.loads(rem.search_reminders("dentist"))
    assert len(by_title) == 1 and by_title[0]["title"] == "Call dentist"

    by_notes = json.loads(rem.search_reminders("appointment"))
    assert len(by_notes) == 1 and by_notes[0]["title"] == "Call dentist"


def test_search_reminders_includes_completed(rem):
    rem.create_reminder("Walk dog")
    rem.complete_reminder("walk")
    results = json.loads(rem.search_reminders("walk"))
    assert len(results) == 1
    assert results[0]["done"] is True
