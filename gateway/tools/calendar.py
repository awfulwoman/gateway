from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gateway.config import GCalConfig

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_config: GCalConfig | None = None
_service = None


def init(config: GCalConfig) -> None:
    global _config
    _config = config


def _get_service():
    global _service
    if _service is not None:
        return _service
    assert _config and _config.token_path, "Google Calendar not configured (GATEWAY_GCAL__TOKEN_PATH required)"

    creds = Credentials.from_authorized_user_file(_config.token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        try:
            with open(_config.token_path, "w") as f:
                f.write(creds.to_json())
        except OSError:
            pass

    _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _encode_id(calendar_id: str, event_id: str) -> str:
    return f"{calendar_id}::{event_id}"


def _split_id(event_id: str) -> tuple[str, str]:
    if "::" in event_id:
        cal_id, ev_id = event_id.split("::", 1)
        return cal_id, ev_id
    return "primary", event_id


def _ns_date(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    if not dt.tzinfo:
        dt = dt.astimezone()
    return dt.isoformat()


def _event_to_dict(ev: dict, cal_summary: str) -> dict:
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "event_id": _encode_id(ev.get("_calendar_id", ""), ev.get("id", "")),
        "title": ev.get("summary", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "all_day": "date" in start,
        "location": ev.get("location", ""),
        "notes": ev.get("description", ""),
        "calendar": cal_summary,
        "url": ev.get("htmlLink", ""),
    }


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


def _list_calendars(service) -> list[dict]:
    result = service.calendarList().list().execute()
    return result.get("items", [])


def _resolve_calendar_id(service, calendar_name: str) -> str:
    if not calendar_name:
        return "primary"
    for cal in _list_calendars(service):
        if cal.get("summary", "").lower() == calendar_name.lower():
            return cal["id"]
    return "primary"


def list_calendars() -> str:
    """List all available calendars with their names and identifiers."""
    service = _get_service()
    results = [
        {"name": c.get("summary", ""), "id": c.get("id", ""), "color": c.get("backgroundColor", "")}
        for c in _list_calendars(service)
    ]
    return json.dumps(results)


def list_calendar_events(period: str) -> str:
    """List calendar events for a time period. period can be: 'today', 'tomorrow', 'week' (next 7 days), 'month' (next 30 days), or a custom range as 'YYYY-MM-DD:YYYY-MM-DD'."""
    service = _get_service()
    start, end = _parse_period(period)

    results = []
    for cal in _list_calendars(service):
        cal_id, cal_summary = cal["id"], cal.get("summary", "")
        resp = service.events().list(
            calendarId=cal_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        for ev in resp.get("items", []):
            ev["_calendar_id"] = cal_id
            results.append(_event_to_dict(ev, cal_summary))

    results.sort(key=lambda e: e["start"])
    return json.dumps(results)


def search_calendar_events(query: str, days_ahead: int = 90) -> str:
    """Search calendar events by title, location, or notes. Searches forward from today up to days_ahead days (default 90)."""
    service = _get_service()
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    results = []
    for cal in _list_calendars(service):
        cal_id, cal_summary = cal["id"], cal.get("summary", "")
        resp = service.events().list(
            calendarId=cal_id,
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            q=query,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        for ev in resp.get("items", []):
            ev["_calendar_id"] = cal_id
            results.append(_event_to_dict(ev, cal_summary))

    return json.dumps(results)


def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str,
    location: str = "",
    notes: str = "",
    calendar_name: str = "",
) -> str:
    """Create a calendar event. Dates in ISO 8601 format (e.g. 2026-04-10T14:00:00). calendar_name is optional and defaults to the system default calendar."""
    service = _get_service()
    cal_id = _resolve_calendar_id(service, calendar_name)

    body: dict = {
        "summary": title,
        "start": {"dateTime": _ns_date(start_iso)},
        "end": {"dateTime": _ns_date(end_iso)},
    }
    if location:
        body["location"] = location
    if notes:
        body["description"] = notes

    try:
        service.events().insert(calendarId=cal_id, body=body).execute()
    except HttpError as e:
        return json.dumps({"status": "error", "message": f"Failed to create event: {title} ({e})"})

    return json.dumps({"status": "created", "title": title, "start": start_iso, "end": end_iso})


def update_calendar_event(
    event_id: str,
    title: str = "",
    start_iso: str = "",
    end_iso: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    """Update fields on an existing calendar event by event_id. Only supplied (non-empty) fields are changed."""
    service = _get_service()
    cal_id, ev_id = _split_id(event_id)

    body: dict = {}
    if title:
        body["summary"] = title
    if start_iso:
        body["start"] = {"dateTime": _ns_date(start_iso)}
    if end_iso:
        body["end"] = {"dateTime": _ns_date(end_iso)}
    if location:
        body["location"] = location
    if notes:
        body["description"] = notes

    try:
        service.events().patch(calendarId=cal_id, eventId=ev_id, body=body).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})
        return json.dumps({"status": "error", "message": f"Failed to update event: {e}"})

    return json.dumps({"status": "updated", "event_id": event_id})


def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event by its event_id (obtained from list_calendar_events or search_calendar_events)."""
    service = _get_service()
    cal_id, ev_id = _split_id(event_id)

    try:
        service.events().delete(calendarId=cal_id, eventId=ev_id).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})
        return json.dumps({"status": "error", "message": f"Failed to delete event: {e}"})

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
