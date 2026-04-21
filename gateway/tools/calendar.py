from __future__ import annotations
import json
import threading
from datetime import datetime, timedelta, timezone

_ek_store = None


def _get_store():
    global _ek_store
    if _ek_store is not None:
        return _ek_store
    import EventKit

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    try:
        store.requestFullAccessToEventsWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


def _ns_date(iso: str):
    import Foundation
    dt = datetime.fromisoformat(iso)
    if not dt.tzinfo:
        dt = dt.astimezone()
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def _event_to_dict(ev) -> dict:
    return {
        "event_id": str(ev.eventIdentifier() or ""),
        "title": str(ev.title() or ""),
        "start": str(ev.startDate()),
        "end": str(ev.endDate()),
        "all_day": bool(ev.isAllDay()),
        "location": str(ev.location() or ""),
        "notes": str(ev.notes() or ""),
        "calendar": str(ev.calendar().title() or ""),
        "url": str(ev.URL() or ""),
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


def list_calendars() -> str:
    """List all available calendars with their names and identifiers."""
    import EventKit
    store = _get_store()
    cals = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    results = [
        {"name": str(c.title()), "id": str(c.calendarIdentifier()), "color": str(c.color())}
        for c in (cals or [])
    ]
    return json.dumps(results)


def list_calendar_events(period: str) -> str:
    """List calendar events for a time period. period can be: 'today', 'tomorrow', 'week' (next 7 days), 'month' (next 30 days), or a custom range as 'YYYY-MM-DD:YYYY-MM-DD'."""
    import EventKit
    import Foundation
    store = _get_store()

    start, end = _parse_period(period)
    ns_start = Foundation.NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
    ns_end = Foundation.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())
    calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, calendars)
    events = store.eventsMatchingPredicate_(pred)

    results = sorted([_event_to_dict(ev) for ev in (events or [])], key=lambda e: e["start"])
    return json.dumps(results)


def search_calendar_events(query: str, days_ahead: int = 90) -> str:
    """Search calendar events by title, location, or notes. Searches forward from today up to days_ahead days (default 90)."""
    import EventKit
    import Foundation
    store = _get_store()

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    ns_start = Foundation.NSDate.dateWithTimeIntervalSince1970_(now.timestamp())
    ns_end = Foundation.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())
    calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, calendars)
    events = store.eventsMatchingPredicate_(pred)

    q = query.lower()
    results = [
        _event_to_dict(ev) for ev in (events or [])
        if q in str(ev.title() or "").lower()
        or q in str(ev.location() or "").lower()
        or q in str(ev.notes() or "").lower()
    ]
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
    import EventKit
    store = _get_store()

    event = EventKit.EKEvent.eventWithEventStore_(store)
    event.setTitle_(title)
    event.setStartDate_(_ns_date(start_iso))
    event.setEndDate_(_ns_date(end_iso))
    if location:
        event.setLocation_(location)
    if notes:
        event.setNotes_(notes)

    cal = None
    if calendar_name:
        cals = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
        for c in (cals or []):
            if str(c.title()).lower() == calendar_name.lower():
                cal = c
                break
    event.setCalendar_(cal or store.defaultCalendarForNewEvents())

    ok = store.saveEvent_span_commit_error_(event, EventKit.EKSpanThisEvent, True, None)
    if ok:
        return json.dumps({"status": "created", "title": title, "start": start_iso, "end": end_iso})
    return json.dumps({"status": "error", "message": f"Failed to create event: {title}"})


def update_calendar_event(
    event_id: str,
    title: str = "",
    start_iso: str = "",
    end_iso: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    """Update fields on an existing calendar event by event_id. Only supplied (non-empty) fields are changed."""
    import EventKit
    store = _get_store()

    event = store.eventWithIdentifier_(event_id)
    if event is None:
        return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})
    if title:
        event.setTitle_(title)
    if start_iso:
        event.setStartDate_(_ns_date(start_iso))
    if end_iso:
        event.setEndDate_(_ns_date(end_iso))
    if location:
        event.setLocation_(location)
    if notes:
        event.setNotes_(notes)

    ok = store.saveEvent_span_commit_error_(event, EventKit.EKSpanThisEvent, True, None)
    if ok:
        return json.dumps({"status": "updated", "event_id": event_id})
    return json.dumps({"status": "error", "message": "Failed to update event"})


def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event by its event_id (obtained from list_calendar_events or search_calendar_events)."""
    import EventKit
    store = _get_store()

    event = store.eventWithIdentifier_(event_id)
    if event is None:
        return json.dumps({"status": "error", "message": f"Event not found: {event_id}"})
    ok = store.removeEvent_span_commit_error_(event, EventKit.EKSpanThisEvent, True, None)
    if ok:
        return json.dumps({"status": "deleted", "event_id": event_id})
    return json.dumps({"status": "error", "message": "Failed to delete event"})


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
