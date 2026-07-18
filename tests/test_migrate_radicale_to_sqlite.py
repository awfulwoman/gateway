from __future__ import annotations
import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path
import icalendar
import gateway.reminders.store as store

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_radicale_to_sqlite.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("migrate_radicale_to_sqlite", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migrate = _load_script()


class _Parent:
    def __init__(self, name):
        self.name = name


class FakeTodo:
    def __init__(self, vtodo, parent_name):
        self.icalendar_component = vtodo
        self.parent = _Parent(parent_name)


class FakeCalendar:
    def __init__(self, name, todos):
        self.name = name
        self._todos = todos

    def get_supported_components(self):
        return ["VTODO"]

    def get_todos(self, include_completed=False):
        return self._todos


class FakePrincipal:
    def __init__(self, calendars):
        self._calendars = calendars

    def calendars(self):
        return self._calendars


class FakeClient:
    def __init__(self, calendars):
        self._principal = FakePrincipal(calendars)

    def principal(self):
        return self._principal


def make_vtodo(uid, summary, due=None, priority=0, status="NEEDS-ACTION", description="", completed=None):
    todo = icalendar.Todo()
    todo.add("uid", uid)
    todo.add("summary", summary)
    todo.add("dtstamp", datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc))
    todo.add("status", status)
    if description:
        todo.add("description", description)
    if priority:
        todo.add("priority", priority)
    if due is not None:
        todo.add("due", due)
    if completed is not None:
        todo.add("completed", completed)
    return todo


def test_extract_location_arrive():
    notes, name, trigger = migrate._extract_location("some notes\n[location: arrive Tesco Express]")
    assert notes == "some notes"
    assert name == "Tesco Express"
    assert trigger == "arrive"


def test_extract_location_leave():
    _, name, trigger = migrate._extract_location("[location: leave Home]")
    assert name == "Home"
    assert trigger == "leave"


def test_extract_location_none():
    notes, name, trigger = migrate._extract_location("just notes")
    assert notes == "just notes"
    assert name is None
    assert trigger == "arrive"


def test_to_rfc3339_date_only():
    assert migrate._to_rfc3339(date(2026, 7, 20)) == "2026-07-20"


def test_to_rfc3339_datetime_utc():
    dt = datetime(2026, 7, 20, 9, 15, 0, tzinfo=timezone.utc)
    assert migrate._to_rfc3339(dt) == "2026-07-20T09:15:00Z"


def test_to_rfc3339_none():
    assert migrate._to_rfc3339(None) is None


def test_todo_to_reminder_maps_fields():
    vtodo = make_vtodo("uid-1", "Buy milk", due=date(2026, 7, 20), priority=1, description="get oat milk")
    todo = FakeTodo(vtodo, parent_name="Shopping")
    reminder = migrate._todo_to_reminder(todo)
    assert reminder["id"] == "uid-1"
    assert reminder["title"] == "Buy milk"
    assert reminder["due"] == "2026-07-20"
    assert reminder["priority"] == 1
    assert reminder["list"] == "Shopping"
    assert reminder["notes"] == "get oat milk"
    assert reminder["done"] is False
    assert reminder["_place_name"] is None


def test_todo_to_reminder_extracts_location_marker():
    vtodo = make_vtodo("uid-2", "Buy eggs", description="[location: arrive Tesco]")
    todo = FakeTodo(vtodo, parent_name="Reminders")
    reminder = migrate._todo_to_reminder(todo)
    assert reminder["_place_name"] == "Tesco"
    assert reminder["_trigger"] == "arrive"
    assert reminder["notes"] is None


def test_todo_to_reminder_completed():
    completed_dt = datetime(2026, 7, 18, 10, 0, 0, tzinfo=timezone.utc)
    vtodo = make_vtodo("uid-3", "Walk dog", status="COMPLETED", completed=completed_dt)
    todo = FakeTodo(vtodo, parent_name="Reminders")
    reminder = migrate._todo_to_reminder(todo)
    assert reminder["done"] is True
    assert reminder["completed_at"] == "2026-07-18T10:00:00Z"


def test_main_migrates_and_resolves_location(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS__BASE_URL", "https://radicale.example.com")
    monkeypatch.setenv("GATEWAY_REMINDERS__USERNAME", "charlie")
    monkeypatch.setenv("GATEWAY_REMINDERS__PASSWORD", "pw")
    monkeypatch.setenv("GATEWAY_REMINDERS__DB_PATH", str(tmp_path / "reminders.db"))
    monkeypatch.setenv("GATEWAY_REMINDERS__NOMINATIM_URL", "https://nominatim.example.com")

    vtodo1 = make_vtodo("uid-a", "Buy milk", due=date(2026, 7, 20))
    vtodo2 = make_vtodo("uid-b", "Buy eggs", description="[location: arrive Tesco]")
    cal = FakeCalendar("Shopping", [
        FakeTodo(vtodo1, parent_name="Shopping"),
        FakeTodo(vtodo2, parent_name="Shopping"),
    ])

    monkeypatch.setattr(migrate.caldav, "DAVClient", lambda **kw: FakeClient([cal]))
    monkeypatch.setattr(migrate.geocode, "forward", lambda q: {"name": "Tesco Express", "lat": 51.5, "lon": -0.1})

    migrate.main()

    stored = store.list_reminders(include_deleted=False)
    assert len(stored) == 2
    by_id = {r["id"]: r for r in stored}
    assert by_id["uid-a"]["due"] == "2026-07-20"
    assert by_id["uid-b"]["location"]["lat"] == 51.5
    assert by_id["uid-b"]["location"]["name"] == "Tesco Express"


def test_main_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS__BASE_URL", "https://radicale.example.com")
    monkeypatch.setenv("GATEWAY_REMINDERS__DB_PATH", str(tmp_path / "reminders.db"))
    monkeypatch.setenv("GATEWAY_REMINDERS__NOMINATIM_URL", "https://nominatim.example.com")
    monkeypatch.setattr(sys, "argv", ["migrate_radicale_to_sqlite.py", "--dry-run"])

    vtodo = make_vtodo("uid-c", "Buy milk")
    cal = FakeCalendar("Reminders", [FakeTodo(vtodo, parent_name="Reminders")])
    monkeypatch.setattr(migrate.caldav, "DAVClient", lambda **kw: FakeClient([cal]))

    migrate.main()

    assert store.list_reminders(include_deleted=False) == []


def test_main_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS__BASE_URL", "https://radicale.example.com")
    monkeypatch.setenv("GATEWAY_REMINDERS__DB_PATH", str(tmp_path / "reminders.db"))
    monkeypatch.setenv("GATEWAY_REMINDERS__NOMINATIM_URL", "https://nominatim.example.com")

    vtodo = make_vtodo("uid-d", "Buy milk")
    cal = FakeCalendar("Reminders", [FakeTodo(vtodo, parent_name="Reminders")])
    monkeypatch.setattr(migrate.caldav, "DAVClient", lambda **kw: FakeClient([cal]))

    migrate.main()
    migrate.main()

    assert len(store.list_reminders(include_deleted=False)) == 1
