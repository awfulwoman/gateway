from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
import pytest
import gateway.tools.calendar as calendar
from gateway.config import CalendarServerConfig


@pytest.fixture
def cal(calendar_server, calendar_server_token):
    calendar.init(CalendarServerConfig(base_url=calendar_server, bearer_token=calendar_server_token))
    return calendar


def _at(days_from_now: int, hour: int = 9) -> str:
    """A UTC instant `days_from_now` days out, so tests stay valid regardless of
    when they run (rather than hardcoding a date that eventually falls outside a
    'month'/'week'-relative window)."""
    dt = (datetime.now(timezone.utc) + timedelta(days=days_from_now)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- pure helpers ---

@pytest.mark.parametrize("period", ["today", "tomorrow", "week", "month"])
def test_parse_period_known(period):
    start, end = calendar._parse_period(period)
    assert start < end


def test_parse_period_custom_range():
    start, end = calendar._parse_period("2026-06-01:2026-06-10")
    assert start.date().isoformat() == "2026-06-01"
    assert end.date().isoformat() == "2026-06-10"


def test_parse_period_invalid():
    with pytest.raises(ValueError):
        calendar._parse_period("nonsense")


def test_to_server_instant_interprets_naive_as_local():
    result = calendar._to_server_instant("2026-06-08T14:00:00")
    expected = datetime(2026, 6, 8, 14, 0, 0).astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert result == expected


def test_to_server_instant_handles_z_suffix():
    assert calendar._to_server_instant("2026-06-08T14:00:00Z") == "2026-06-08T14:00:00Z"


def test_to_external_maps_id_to_event_id():
    ev = {
        "id": "abc123", "title": "Standup", "start": "2026-06-07T09:00:00Z", "end": "2026-06-07T09:30:00Z",
        "all_day": False, "location": "Office", "notes": "daily sync", "calendar": "Work", "url": "https://x",
    }
    assert calendar._to_external(ev) == {
        "event_id": "abc123", "title": "Standup", "start": "2026-06-07T09:00:00Z", "end": "2026-06-07T09:30:00Z",
        "all_day": False, "location": "Office", "notes": "daily sync", "calendar": "Work", "url": "https://x",
    }


def test_to_external_defaults_missing_optionals_to_empty_string():
    ev = {"id": "abc", "title": "X", "start": "s", "end": "e", "all_day": True, "calendar": "Calendar"}
    d = calendar._to_external(ev)
    assert d["location"] == "" and d["notes"] == "" and d["url"] == ""


# --- tool functions ---

def test_list_calendars_empty(cal):
    assert json.loads(cal.list_calendars()) == []


def test_create_calendar_event_defaults_to_default_calendar(cal):
    result = json.loads(cal.create_calendar_event("Trip", _at(5), _at(5, hour=10)))
    assert result["status"] == "created"
    assert result["title"] == "Trip"
    assert json.loads(cal.list_calendars()) == [{"name": "Calendar"}]


def test_create_calendar_event_in_named_calendar(cal):
    cal.create_calendar_event("Trip", _at(5), _at(5, hour=10), calendar_name="Myrtle")
    events = json.loads(cal.list_calendar_events("month"))
    assert len(events) == 1
    assert events[0]["calendar"] == "Myrtle"
    assert events[0]["title"] == "Trip"


def test_create_calendar_event_with_location_and_notes(cal):
    cal.create_calendar_event("Dentist", _at(5), _at(5, hour=10), location="Clinic", notes="bring insurance card")
    events = json.loads(cal.list_calendar_events("month"))
    assert events[0]["location"] == "Clinic"
    assert events[0]["notes"] == "bring insurance card"


def test_create_calendar_event_rejects_empty_title(cal):
    result = json.loads(cal.create_calendar_event("", _at(5), _at(5, hour=10)))
    assert result["status"] == "error"
    assert json.loads(cal.list_calendar_events("month")) == []


def test_list_calendar_events_sorted_by_start(cal):
    cal.create_calendar_event("Later", _at(5, hour=15), _at(5, hour=16))
    cal.create_calendar_event("Earlier", _at(5, hour=9), _at(5, hour=10))
    events = json.loads(cal.list_calendar_events("month"))
    assert [e["title"] for e in events] == ["Earlier", "Later"]


def test_search_calendar_events_matches_title_location_notes(cal):
    cal.create_calendar_event("Call dentist", _at(5), _at(5, hour=10), notes="reschedule appointment")
    cal.create_calendar_event("Buy stamps", _at(6), _at(6, hour=10))

    by_title = json.loads(cal.search_calendar_events("dentist"))
    assert len(by_title) == 1 and by_title[0]["title"] == "Call dentist"

    by_notes = json.loads(cal.search_calendar_events("appointment"))
    assert len(by_notes) == 1 and by_notes[0]["title"] == "Call dentist"


def test_update_calendar_event_changes_only_supplied_fields(cal):
    created = json.loads(cal.create_calendar_event("Standup", _at(5), _at(5, hour=10), notes="daily"))
    events = json.loads(cal.list_calendar_events("month"))
    event_id = events[0]["event_id"]

    result = json.loads(cal.update_calendar_event(event_id, title="Standup (moved)"))
    assert result == {"status": "updated", "event_id": event_id}

    updated = json.loads(cal.list_calendar_events("month"))[0]
    assert updated["title"] == "Standup (moved)"
    assert updated["notes"] == "daily"  # untouched


def test_update_calendar_event_not_found(cal):
    result = json.loads(cal.update_calendar_event("no-such-id", title="x"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_delete_calendar_event(cal):
    cal.create_calendar_event("Old meeting", _at(5), _at(5, hour=10))
    event_id = json.loads(cal.list_calendar_events("month"))[0]["event_id"]

    result = json.loads(cal.delete_calendar_event(event_id))
    assert result == {"status": "deleted", "event_id": event_id}
    assert json.loads(cal.list_calendar_events("month")) == []


def test_delete_calendar_event_not_found(cal):
    result = json.loads(cal.delete_calendar_event("no-such-id"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()
