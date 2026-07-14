from __future__ import annotations
import json
import icalendar
import pytest
import gateway.tools.reminders as reminders
from gateway.config import RemindersConfig


class FakeTodo:
    def __init__(self, icalendar_component, parent):
        self.icalendar_component = icalendar_component
        self.parent = parent

    def complete(self):
        self.icalendar_component["status"] = "COMPLETED"

    def delete(self):
        self.parent._todos.remove(self)


class FakeCalendar:
    def __init__(self, name):
        self.name = name
        self.url = f"https://radicale.example.com/charlie/{name}/"
        self._todos: list[FakeTodo] = []

    def get_supported_components(self):
        return ["VTODO"]

    def get_todos(self, include_completed=False):
        todos = list(self._todos)
        if not include_completed:
            todos = [t for t in todos if str(t.icalendar_component.get("status", "")) != "COMPLETED"]
        return todos

    def add_todo(self, ical):
        cal = icalendar.Calendar.from_ical(ical)
        vtodo = next(iter(cal.walk("VTODO")))
        todo = FakeTodo(vtodo, self)
        self._todos.append(todo)
        return todo


class FakePrincipal:
    def __init__(self, calendars):
        self._calendars = calendars

    def calendars(self):
        return self._calendars

    def make_calendar(self, name, supported_calendar_component_set=None):
        cal = FakeCalendar(name)
        self._calendars.append(cal)
        return cal


class FakeClient:
    def __init__(self, calendars):
        self._principal = FakePrincipal(calendars)

    def principal(self):
        return self._principal


@pytest.fixture
def calendars(monkeypatch):
    cals: list[FakeCalendar] = []
    reminders.init(RemindersConfig(base_url="https://radicale.example.com", username="charlie", password="pw"))
    monkeypatch.setattr(reminders, "_get_client", lambda: FakeClient(cals))
    return cals


def test_list_reminder_lists_empty(calendars):
    assert json.loads(reminders.list_reminder_lists()) == []


def test_create_reminder_creates_default_list(calendars):
    result = json.loads(reminders.create_reminder("Buy milk"))
    assert result == {"status": "created", "title": "Buy milk"}

    lists = json.loads(reminders.list_reminder_lists())
    assert lists == [{"name": "Reminders", "id": "https://radicale.example.com/charlie/Reminders/"}]


def test_create_reminder_in_named_list(calendars):
    calendars.append(FakeCalendar("Shopping"))
    reminders.create_reminder("Buy milk", list_name="Shopping", priority=1)
    items = json.loads(reminders.list_reminders())
    assert items == [{
        "title": "Buy milk", "completed": False, "due": None,
        "notes": "", "priority": 1, "list": "Shopping",
    }]


def test_create_reminder_unknown_list_falls_back_to_default(calendars):
    reminders.create_reminder("Buy milk", list_name="Shopping")
    items = json.loads(reminders.list_reminders())
    assert items[0]["list"] == "Reminders"


def test_create_reminder_with_due_and_notes(calendars):
    calendars.append(FakeCalendar("Bills"))
    reminders.create_reminder("Pay rent", due_iso="2026-08-01", notes="via bank transfer", list_name="Bills")
    items = json.loads(reminders.list_reminders(list_name="Bills"))
    assert items[0]["due"] == "2026-08-01"
    assert items[0]["notes"] == "via bank transfer"


def test_list_reminders_filters_by_missing_list(calendars):
    reminders.create_reminder("Buy milk", list_name="Shopping")
    assert json.loads(reminders.list_reminders(list_name="Nonexistent")) == []


def test_create_reminder_with_location_stores_note(calendars):
    reminders.create_reminder("Buy eggs", location_name="Tesco", arrive_or_leave="arrive")
    items = json.loads(reminders.list_reminders())
    assert "Tesco" in items[0]["notes"]
    assert "arrive" in items[0]["notes"]


def test_complete_reminder(calendars):
    reminders.create_reminder("Walk dog")
    result = json.loads(reminders.complete_reminder("walk"))
    assert result == {"status": "completed", "title": "Walk dog"}

    assert json.loads(reminders.list_reminders()) == []
    completed = json.loads(reminders.list_reminders(include_completed=True))
    assert completed[0]["completed"] is True


def test_complete_reminder_not_found(calendars):
    result = json.loads(reminders.complete_reminder("nonexistent"))
    assert result == {"status": "not_found", "message": "No incomplete reminder matching: nonexistent"}


def test_delete_reminder(calendars):
    reminders.create_reminder("Old task")
    result = json.loads(reminders.delete_reminder("old"))
    assert result == {"status": "deleted", "title": "Old task"}
    assert json.loads(reminders.list_reminders(include_completed=True)) == []


def test_delete_reminder_not_found(calendars):
    result = json.loads(reminders.delete_reminder("nonexistent"))
    assert result == {"status": "not_found", "message": "No reminder matching: nonexistent"}


def test_search_reminders_matches_title_and_notes(calendars):
    reminders.create_reminder("Call dentist", notes="reschedule appointment")
    reminders.create_reminder("Buy stamps")

    by_title = json.loads(reminders.search_reminders("dentist"))
    assert len(by_title) == 1 and by_title[0]["title"] == "Call dentist"

    by_notes = json.loads(reminders.search_reminders("appointment"))
    assert len(by_notes) == 1 and by_notes[0]["title"] == "Call dentist"


def test_search_reminders_includes_completed(calendars):
    reminders.create_reminder("Walk dog")
    reminders.complete_reminder("walk")
    results = json.loads(reminders.search_reminders("walk"))
    assert len(results) == 1
    assert results[0]["completed"] is True
