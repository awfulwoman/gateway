from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from googleapiclient.errors import HttpError
import gateway.tools.calendar as calendar


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeCalendarList:
    def __init__(self, items):
        self._items = items

    def list(self):
        return _Exec({"items": self._items})


class _FakeEvents:
    def __init__(self, list_items=None, raise_on: dict | None = None):
        self._list_items = list_items if list_items is not None else []
        self._raise_on = raise_on or {}
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return _Exec({"items": self._list_items})

    def insert(self, **kwargs):
        self.calls.append(("insert", kwargs))
        if "insert" in self._raise_on:
            raise self._raise_on["insert"]
        return _Exec({"id": "new1"})

    def patch(self, **kwargs):
        self.calls.append(("patch", kwargs))
        if "patch" in self._raise_on:
            raise self._raise_on["patch"]
        return _Exec({})

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        if "delete" in self._raise_on:
            raise self._raise_on["delete"]
        return _Exec({})


class _FakeService:
    def __init__(self, calendars, events: _FakeEvents | None = None):
        self._calendars = calendars
        self._events = events if events is not None else _FakeEvents()

    def calendarList(self):
        return _FakeCalendarList(self._calendars)

    def events(self):
        return self._events


def _http_error(status: int) -> HttpError:
    class _Resp:
        pass

    resp = _Resp()
    resp.status = status
    resp.reason = "error"
    return HttpError(resp, b"{}")


# --- pure helpers ---

def test_event_id_round_trip():
    encoded = calendar._encode_id("cal-abc", "ev-123")
    assert encoded == "cal-abc::ev-123"
    assert calendar._split_id(encoded) == ("cal-abc", "ev-123")


def test_split_id_falls_back_to_primary_without_delimiter():
    assert calendar._split_id("bare-id") == ("primary", "bare-id")


def test_event_to_dict_timed():
    ev = {
        "_calendar_id": "cal1",
        "id": "e1",
        "summary": "Stand-up",
        "start": {"dateTime": "2026-06-07T09:00:00+02:00"},
        "end": {"dateTime": "2026-06-07T09:30:00+02:00"},
        "location": "Office",
        "description": "daily sync",
        "htmlLink": "https://calendar.google.com/e1",
    }
    d = calendar._event_to_dict(ev, "Work")
    assert d == {
        "event_id": "cal1::e1",
        "title": "Stand-up",
        "start": "2026-06-07T09:00:00+02:00",
        "end": "2026-06-07T09:30:00+02:00",
        "all_day": False,
        "location": "Office",
        "notes": "daily sync",
        "calendar": "Work",
        "url": "https://calendar.google.com/e1",
    }


def test_event_to_dict_all_day():
    ev = {
        "_calendar_id": "cal1",
        "id": "e2",
        "summary": "Holiday",
        "start": {"date": "2026-06-08"},
        "end": {"date": "2026-06-09"},
    }
    d = calendar._event_to_dict(ev, "Work")
    assert d["all_day"] is True
    assert d["start"] == "2026-06-08"
    assert d["location"] == ""
    assert d["notes"] == ""
    assert d["url"] == ""


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


# --- tool functions ---

def test_list_calendars():
    service = _FakeService([{"summary": "Work", "id": "c1", "backgroundColor": "#0000ff"}])
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.list_calendars())
    assert result == [{"name": "Work", "id": "c1", "color": "#0000ff"}]


def test_list_calendar_events_aggregates_and_sorts():
    events = _FakeEvents(list_items=[
        {"id": "e2", "summary": "Later", "start": {"dateTime": "2026-06-07T15:00:00+02:00"}, "end": {"dateTime": "2026-06-07T15:30:00+02:00"}},
        {"id": "e1", "summary": "Earlier", "start": {"dateTime": "2026-06-07T09:00:00+02:00"}, "end": {"dateTime": "2026-06-07T09:30:00+02:00"}},
    ])
    service = _FakeService([{"summary": "Work", "id": "c1"}], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.list_calendar_events("today"))
    assert [e["title"] for e in result] == ["Earlier", "Later"]
    assert all(e["calendar"] == "Work" for e in result)
    assert events.calls[0][1]["calendarId"] == "c1"


def test_search_calendar_events_passes_query():
    events = _FakeEvents(list_items=[{"id": "e1", "summary": "Dentist", "start": {"dateTime": "2026-06-07T09:00:00+02:00"}, "end": {"dateTime": "2026-06-07T09:30:00+02:00"}}])
    service = _FakeService([{"summary": "Work", "id": "c1"}], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.search_calendar_events("dentist", days_ahead=30))
    assert result[0]["title"] == "Dentist"
    assert events.calls[0][1]["q"] == "dentist"


def test_create_calendar_event_resolves_calendar_and_inserts():
    events = _FakeEvents()
    service = _FakeService([{"summary": "Myrtle", "id": "myrtle-id"}], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.create_calendar_event(
            "Trip", "2026-06-08T14:00:00", "2026-06-08T15:00:00", calendar_name="myrtle",
        ))
    assert result["status"] == "created"
    call_kwargs = events.calls[0][1]
    assert call_kwargs["calendarId"] == "myrtle-id"
    assert call_kwargs["body"]["summary"] == "Trip"


def test_create_calendar_event_defaults_to_primary():
    events = _FakeEvents()
    service = _FakeService([{"summary": "Work", "id": "c1"}], events)
    with patch.object(calendar, "_get_service", return_value=service):
        calendar.create_calendar_event("Trip", "2026-06-08T14:00:00", "2026-06-08T15:00:00")
    assert events.calls[0][1]["calendarId"] == "primary"


def test_create_calendar_event_handles_error():
    events = _FakeEvents(raise_on={"insert": _http_error(400)})
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.create_calendar_event("Trip", "2026-06-08T14:00:00", "2026-06-08T15:00:00"))
    assert result["status"] == "error"


def test_update_calendar_event_sends_only_nonempty_fields():
    events = _FakeEvents()
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.update_calendar_event("cal1::e1", title="New title"))
    assert result == {"status": "updated", "event_id": "cal1::e1"}
    call_kwargs = events.calls[0][1]
    assert call_kwargs["calendarId"] == "cal1"
    assert call_kwargs["eventId"] == "e1"
    assert call_kwargs["body"] == {"summary": "New title"}


def test_update_calendar_event_not_found():
    events = _FakeEvents(raise_on={"patch": _http_error(404)})
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.update_calendar_event("cal1::missing", title="x"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_delete_calendar_event():
    events = _FakeEvents()
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.delete_calendar_event("cal1::e1"))
    assert result == {"status": "deleted", "event_id": "cal1::e1"}
    assert events.calls[0][1] == {"calendarId": "cal1", "eventId": "e1"}


def test_delete_calendar_event_defaults_calendar_when_no_delimiter():
    events = _FakeEvents()
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        calendar.delete_calendar_event("bare-id")
    assert events.calls[0][1] == {"calendarId": "primary", "eventId": "bare-id"}


def test_delete_calendar_event_not_found():
    events = _FakeEvents(raise_on={"delete": _http_error(404)})
    service = _FakeService([], events)
    with patch.object(calendar, "_get_service", return_value=service):
        result = json.loads(calendar.delete_calendar_event("cal1::missing"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()
