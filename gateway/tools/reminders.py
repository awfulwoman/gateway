from __future__ import annotations
import json
import threading
from datetime import datetime

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
        store.requestFullAccessToRemindersWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeReminder, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


def _fetch_reminders(store, include_completed: bool) -> list:
    done = threading.Event()
    found: list = []

    if include_completed:
        pred = store.predicateForRemindersInCalendars_(None)
    else:
        pred = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
            None, None, None
        )

    def cb(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    done.wait(timeout=10)
    return found


def _geocode(location_name: str):
    """Return (lat, lon) for a location name, or None if geocoding fails."""
    import CoreLocation
    done = threading.Event()
    result = [None]

    geocoder = CoreLocation.CLGeocoder.alloc().init()

    def cb(placemarks, error):
        if placemarks and len(placemarks) > 0:
            loc = placemarks[0].location()
            if loc:
                coord = loc.coordinate()
                result[0] = (coord.latitude, coord.longitude)
        done.set()

    geocoder.geocodeAddressString_completionHandler_(location_name, cb)
    done.wait(timeout=10)
    return result[0]


def _reminder_to_dict(r) -> dict:
    due = None
    if r.dueDateComponents():
        dc = r.dueDateComponents()
        try:
            due = f"{dc.year():04d}-{dc.month():02d}-{dc.day():02d}"
        except Exception:
            due = str(dc)
    return {
        "title": str(r.title() or ""),
        "completed": bool(r.isCompleted()),
        "due": due,
        "notes": str(r.notes() or ""),
        "priority": int(r.priority()),
        "list": str(r.calendar().title() or ""),
    }


def list_reminder_lists() -> str:
    """List all reminder lists (calendars) with their names and identifiers."""
    import EventKit
    store = _get_store()
    cals = store.calendarsForEntityType_(EventKit.EKEntityTypeReminder)
    results = [{"name": str(c.title()), "id": str(c.calendarIdentifier())} for c in (cals or [])]
    return json.dumps(results)


def list_reminders(include_completed: bool = False, list_name: str = "") -> str:
    """List reminders. Set include_completed=true to include completed reminders. Optionally filter by list_name."""
    store = _get_store()
    found = _fetch_reminders(store, include_completed)

    results = []
    for r in found:
        if list_name and str(r.calendar().title() or "").lower() != list_name.lower():
            continue
        results.append(_reminder_to_dict(r))
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
    """Create a reminder. due_iso is an optional ISO 8601 date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). priority: 0=none, 1=high, 5=medium, 9=low. location_name triggers the reminder on arrival/departure; arrive_or_leave is 'arrive' (default) or 'leave'."""
    import EventKit
    import Foundation

    store = _get_store()
    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(title)
    if notes:
        reminder.setNotes_(notes)
    if priority:
        reminder.setPriority_(priority)

    cal = None
    if list_name:
        cals = store.calendarsForEntityType_(EventKit.EKEntityTypeReminder)
        for c in (cals or []):
            if str(c.title()).lower() == list_name.lower():
                cal = c
                break
    reminder.setCalendar_(cal or store.defaultCalendarForNewReminders())

    if due_iso:
        dt = datetime.fromisoformat(due_iso)
        components = Foundation.NSDateComponents.alloc().init()
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        if dt.hour or dt.minute:
            components.setHour_(dt.hour)
            components.setMinute_(dt.minute)
        reminder.setDueDateComponents_(components)

    if location_name:
        import CoreLocation
        coords = _geocode(location_name)
        alarm = EventKit.EKAlarm.alloc().init()
        proximity = (
            EventKit.EKAlarmProximityLeave
            if arrive_or_leave == "leave"
            else EventKit.EKAlarmProximityEnter
        )
        alarm.setProximity_(proximity)
        struct_loc = EventKit.EKStructuredLocation.locationWithTitle_(location_name)
        if coords:
            cl_loc = CoreLocation.CLLocation.alloc().initWithLatitude_longitude_(coords[0], coords[1])
            struct_loc.setGeoLocation_(cl_loc)
            struct_loc.setRadius_(200)
        alarm.setStructuredLocation_(struct_loc)
        reminder.addAlarm_(alarm)

    ok = store.saveReminder_commit_error_(reminder, True, None)
    if ok:
        result = {"status": "created", "title": title}
        if location_name:
            result["location"] = location_name
            result["geocoded"] = coords is not None
        return json.dumps(result)
    return json.dumps({"status": "error", "message": f"Failed to create reminder: {title}"})


def complete_reminder(title: str) -> str:
    """Mark a reminder as completed by title (case-insensitive substring match)."""
    store = _get_store()
    found = _fetch_reminders(store, False)

    for r in found:
        if title.lower() in str(r.title() or "").lower():
            r.setCompleted_(True)
            store.saveReminder_commit_error_(r, True, None)
            return json.dumps({"status": "completed", "title": str(r.title())})
    return json.dumps({"status": "not_found", "message": f"No incomplete reminder matching: {title}"})


def delete_reminder(title: str) -> str:
    """Delete a reminder by title (case-insensitive substring match). Deletes the first match."""
    store = _get_store()
    found = _fetch_reminders(store, True)

    for r in found:
        if title.lower() in str(r.title() or "").lower():
            ok = store.removeReminder_commit_error_(r, True, None)
            if ok:
                return json.dumps({"status": "deleted", "title": str(r.title())})
            return json.dumps({"status": "error", "message": "Failed to delete reminder"})
    return json.dumps({"status": "not_found", "message": f"No reminder matching: {title}"})


def search_reminders(query: str) -> str:
    """Search reminders by title or notes (case-insensitive). Includes both complete and incomplete."""
    store = _get_store()
    found = _fetch_reminders(store, True)

    q = query.lower()
    results = [
        _reminder_to_dict(r) for r in found
        if q in str(r.title() or "").lower() or q in str(r.notes() or "").lower()
    ]
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
