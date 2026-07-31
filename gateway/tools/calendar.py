from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from gateway.config import CalendarServerConfig
from gateway.calendar_server import store

_config: CalendarServerConfig | None = None


def init(config: CalendarServerConfig) -> None:
    global _config
    _config = config
    store.init(config)


def _parse_period(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "today":
        local = datetime.now().astimezone()
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = local.replace(hour=23, minute=59, second=59, microsecond=0)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if period == "tomorrow":
        local = (datetime.now().astimezone() + timedelta(days=1))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = local.replace(hour=23, minute=59, second=59, microsecond=0)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if period == "week":
        return now, now + timedelta(days=7)
    if period == "month":
        return now, now + timedelta(days=30)
    if ":" in period:
        start_str, end_str = period.split(":", 1)
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        if not start.tzinfo:
            start = start.astimezone()
        if not end.tzinfo:
            end = end.astimezone()
        return start, end
    raise ValueError(f"Unknown period: {period!r}. Use 'today', 'tomorrow', 'week', 'month', or 'YYYY-MM-DD:YYYY-MM-DD'.")


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_server_instant(iso: str) -> str:
    """Normalise an arbitrary ISO 8601 instant (naive, offset-aware, or Z-suffixed)
    into the UTC 'YYYY-MM-DDThh:mm:ssZ' form apple-calendar-server expects. A naive
    input is interpreted as the local system time, matching the prior Google
    Calendar tool's behaviour."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso.endswith("Z") else datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return _iso_utc(dt)


def _to_external(ev: dict) -> dict:
    """Keeps the external tool contract (field names) stable across the Google
    Calendar → apple-calendar-server backend swap, so the CLI formatter and any
    existing consumers of this tool's JSON don't need to change."""
    return {
        "event_id": ev["id"],
        "title": ev["title"],
        "start": ev["start"],
        "end": ev["end"],
        "all_day": ev["all_day"],
        "location": ev.get("location") or "",
        "notes": ev.get("notes") or "",
        "calendar": ev["calendar"],
        "url": ev.get("url") or "",
    }


def list_calendars() -> str:
    """List all available calendars with their names."""
    names = store.list_calendars()
    return json.dumps([{"name": name} for name in names])


def list_calendar_events(period: str) -> str:
    """List calendar events for a time period. period can be: 'today', 'tomorrow', 'week' (next 7 days), 'month' (next 30 days), or a custom range as 'YYYY-MM-DD:YYYY-MM-DD'."""
    start, end = _parse_period(period)
    events = store.list_events(start=_iso_utc(start), end=_iso_utc(end), include_deleted=False)
    events.sort(key=lambda e: e["start"])
    return json.dumps([_to_external(e) for e in events])


def search_calendar_events(query: str, days_ahead: int = 90) -> str:
    """Search calendar events by title, location, or notes. Searches forward from today up to days_ahead days (default 90)."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    events = store.list_events(start=_iso_utc(now), end=_iso_utc(end), include_deleted=False)

    q = query.lower()
    results = [
        e for e in events
        if q in e["title"].lower() or q in (e.get("location") or "").lower() or q in (e.get("notes") or "").lower()
    ]
    results.sort(key=lambda e: e["start"])
    return json.dumps([_to_external(e) for e in results])


def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str,
    location: str = "",
    notes: str = "",
    calendar_name: str = "",
) -> str:
    """Create a calendar event. Dates in ISO 8601 format (e.g. 2026-04-10T14:00:00). calendar_name is optional and defaults to the system default calendar."""
    now = store.now_utc()
    event = {
        "id": store.new_id(),
        "title": title,
        "notes": notes or None,
        "location": location or None,
        "all_day": False,
        "start": _to_server_instant(start_iso),
        "end": _to_server_instant(end_iso),
        "calendar": calendar_name or None,
        "url": None,
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    try:
        stored = store.upsert(event)
    except ValueError as e:
        return json.dumps({"status": "error", "message": f"Failed to create event: {title} ({e})"})
    return json.dumps({"status": "created", "title": stored["title"], "start": stored["start"], "end": stored["end"]})


def update_calendar_event(
    event_id: str,
    title: str = "",
    start_iso: str = "",
    end_iso: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    """Update fields on an existing calendar event by event_id. Only supplied (non-empty) fields are changed."""
    existing = store.get(event_id)
    if existing is None or existing.get("deleted"):
        return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})

    updated = dict(existing)
    if title:
        updated["title"] = title
    if start_iso:
        updated["start"] = _to_server_instant(start_iso)
    if end_iso:
        updated["end"] = _to_server_instant(end_iso)
    if location:
        updated["location"] = location
    if notes:
        updated["notes"] = notes
    updated["updated_at"] = store.now_after(existing["updated_at"])

    try:
        store.upsert(updated)
    except ValueError as e:
        return json.dumps({"status": "error", "message": f"Failed to update event: {e}"})
    return json.dumps({"status": "updated", "event_id": event_id})


def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event by its event_id (obtained from list_calendar_events or search_calendar_events)."""
    try:
        store.soft_delete(event_id)
    except KeyError:
        return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})
    return json.dumps({"status": "deleted", "event_id": event_id})


def register(mcp) -> None:
    for fn in [
        list_calendars,
        list_calendar_events,
        search_calendar_events,
        create_calendar_event,
        update_calendar_event,
        delete_calendar_event,
    ]:
        mcp.tool()(fn)
