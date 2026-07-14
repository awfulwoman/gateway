from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
import caldav
import icalendar
from gateway.config import RemindersConfig

_config: RemindersConfig | None = None
_client: caldav.DAVClient | None = None

DEFAULT_LIST_NAME = "Reminders"


def init(config: RemindersConfig) -> None:
    global _config, _client
    _config = config
    _client = None


def _get_client() -> caldav.DAVClient:
    global _client
    if _client is None:
        assert _config and _config.base_url, "Reminders not configured (GATEWAY_REMINDERS__BASE_URL required)"
        _client = caldav.DAVClient(url=_config.base_url, username=_config.username, password=_config.password)
    return _client


def _todo_calendars() -> list:
    principal = _get_client().principal()
    return [c for c in principal.calendars() if "VTODO" in c.get_supported_components()]


def _find_calendar(list_name: str):
    for cal in _todo_calendars():
        if str(cal.name or "").lower() == list_name.lower():
            return cal
    return None


def _default_calendar():
    cals = _todo_calendars()
    for cal in cals:
        if str(cal.name or "").lower() == DEFAULT_LIST_NAME.lower():
            return cal
    if cals:
        return cals[0]
    principal = _get_client().principal()
    return principal.make_calendar(name=DEFAULT_LIST_NAME, supported_calendar_component_set=["VTODO"])


def _due_str(vtodo) -> str | None:
    due = vtodo.get("due")
    if not due:
        return None
    dt = due.dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _todo_to_dict(todo) -> dict:
    vtodo = todo.icalendar_component
    status = str(vtodo.get("status", "NEEDS-ACTION"))
    return {
        "title": str(vtodo.get("summary", "")),
        "completed": status == "COMPLETED",
        "due": _due_str(vtodo),
        "notes": str(vtodo.get("description", "")),
        "priority": int(vtodo.get("priority") or 0),
        "list": str(todo.parent.name) if todo.parent else "",
    }


def _build_vtodo_ical(title: str, due_iso: str, notes: str, priority: int) -> str:
    cal = icalendar.Calendar()
    cal.add("prodid", "-//gateway//reminders//EN")
    cal.add("version", "2.0")
    todo = icalendar.Todo()
    todo.add("uid", f"{uuid.uuid4()}@gateway")
    todo.add("summary", title)
    todo.add("dtstamp", datetime.now(timezone.utc))
    todo.add("status", "NEEDS-ACTION")
    if notes:
        todo.add("description", notes)
    if priority:
        todo.add("priority", priority)
    if due_iso:
        dt = datetime.fromisoformat(due_iso)
        todo.add("due", dt if (dt.hour or dt.minute) else dt.date())
    cal.add_component(todo)
    return cal.to_ical().decode("utf-8")


def list_reminder_lists() -> str:
    """List all reminder lists (calendars) with their names and identifiers."""
    results = [{"name": str(cal.name), "id": str(cal.url)} for cal in _todo_calendars()]
    return json.dumps(results)


def list_reminders(include_completed: bool = False, list_name: str = "") -> str:
    """List reminders. Set include_completed=true to include completed reminders. Optionally filter by list_name."""
    if list_name:
        cal = _find_calendar(list_name)
        cals = [cal] if cal else []
    else:
        cals = _todo_calendars()

    results = []
    for cal in cals:
        for todo in cal.get_todos(include_completed=include_completed):
            results.append(_todo_to_dict(todo))
    return json.dumps(results)


def create_reminder(
    title: str,
    due_iso: str = "",
    notes: str = "",
    list_name: str = "",
    priority: int = 0,
    location_name: str = "",
    arrive_or_leave: str = "arrive",
) -> str:
    """Create a reminder. due_iso is an optional ISO 8601 date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). priority: 0=none, 1=high, 5=medium, 9=low. location_name is stored as a plain-text note (CalDAV has no portable geofence trigger); arrive_or_leave is 'arrive' (default) or 'leave'."""
    cal = _find_calendar(list_name) if list_name else None
    if cal is None:
        cal = _default_calendar()

    full_notes = notes
    if location_name:
        marker = f"[location: {arrive_or_leave} {location_name}]"
        full_notes = f"{notes}\n{marker}".strip() if notes else marker

    ical = _build_vtodo_ical(title, due_iso, full_notes, priority)
    cal.add_todo(ical)

    result = {"status": "created", "title": title}
    if location_name:
        result["location"] = location_name
    return json.dumps(result)


def complete_reminder(title: str) -> str:
    """Mark a reminder as completed by title (case-insensitive substring match)."""
    q = title.lower()
    for cal in _todo_calendars():
        for todo in cal.get_todos(include_completed=False):
            summary = str(todo.icalendar_component.get("summary", ""))
            if q in summary.lower():
                todo.complete()
                return json.dumps({"status": "completed", "title": summary})
    return json.dumps({"status": "not_found", "message": f"No incomplete reminder matching: {title}"})


def delete_reminder(title: str) -> str:
    """Delete a reminder by title (case-insensitive substring match). Deletes the first match."""
    q = title.lower()
    for cal in _todo_calendars():
        for todo in cal.get_todos(include_completed=True):
            summary = str(todo.icalendar_component.get("summary", ""))
            if q in summary.lower():
                todo.delete()
                return json.dumps({"status": "deleted", "title": summary})
    return json.dumps({"status": "not_found", "message": f"No reminder matching: {title}"})


def search_reminders(query: str) -> str:
    """Search reminders by title or notes (case-insensitive). Includes both complete and incomplete."""
    q = query.lower()
    results = []
    for cal in _todo_calendars():
        for todo in cal.get_todos(include_completed=True):
            d = _todo_to_dict(todo)
            if q in d["title"].lower() or q in d["notes"].lower():
                results.append(d)
    return json.dumps(results)


def register(mcp) -> None:
    for fn in [
        list_reminder_lists,
        list_reminders,
        create_reminder,
        complete_reminder,
        delete_reminder,
        search_reminders,
    ]:
        mcp.tool()(fn)
