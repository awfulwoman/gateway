from __future__ import annotations
import json
from gateway.config import RemindersConfig, RemindersServerConfig
from gateway.reminders import geocode, store


def init(config: RemindersConfig, reminders_server_config: RemindersServerConfig) -> None:
    store.init(reminders_server_config)
    geocode.init(config)


def list_reminder_lists() -> str:
    """List all reminder lists (distinct list names currently in use)."""
    names = sorted({r["list"] for r in store.list_reminders(include_deleted=False)})
    return json.dumps([{"name": name} for name in names])


def list_reminders(include_completed: bool = False, list_name: str = "") -> str:
    """List reminders. Set include_completed=true to include completed reminders. Optionally filter by list_name."""
    results = store.list_reminders(include_deleted=False, list_name=list_name or None)
    if not include_completed:
        results = [r for r in results if not r["done"]]
    return json.dumps(results)


def create_reminder(
    title: str,
    due_iso: str = "",
    notes: str = "",
    list_name: str = "",
    priority: int = 0,
    location_name: str = "",
    arrive_or_leave: str = "arrive",
    radius_m: int = 150,
) -> str:
    """Create a reminder. due_iso is an optional ISO 8601 date (YYYY-MM-DD) or timestamp
    (YYYY-MM-DDTHH:MM:SSZ). priority: 0=none, 1=high, 5=medium, 9=low. location_name is
    resolved to coordinates via the configured geocoder (fails if it can't be resolved);
    arrive_or_leave is 'arrive' (default) or 'leave'; radius_m is the geofence radius in
    metres (default 150)."""
    location = None
    if location_name:
        resolved = geocode.forward(location_name)
        if resolved is None:
            return json.dumps({"error": f"Could not resolve location: {location_name}"})
        location = {
            "name": resolved["name"],
            "lat": resolved["lat"],
            "lon": resolved["lon"],
            "radius_m": radius_m,
            "trigger": arrive_or_leave,
        }

    now = store.now_utc()
    reminder = {
        "id": store.new_id(),
        "title": title,
        "notes": notes or None,
        "due": due_iso or None,
        "priority": priority,
        "list": list_name,
        "done": False,
        "completed_at": None,
        "location": location,
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    try:
        stored = store.upsert(reminder)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(stored)


def complete_reminder(title: str) -> str:
    """Mark a reminder as completed by title (case-insensitive substring match)."""
    q = title.lower()
    for r in store.list_reminders(include_deleted=False):
        if not r["done"] and q in r["title"].lower():
            now = store.now_after(r["updated_at"])
            r["done"] = True
            r["completed_at"] = now
            r["updated_at"] = now
            stored = store.upsert(r)
            return json.dumps(stored)
    return json.dumps({"status": "not_found", "message": f"No incomplete reminder matching: {title}"})


def delete_reminder(title: str) -> str:
    """Delete a reminder by title (case-insensitive substring match). Deletes the first match."""
    q = title.lower()
    for r in store.list_reminders(include_deleted=False):
        if q in r["title"].lower():
            tombstone = store.soft_delete(r["id"])
            return json.dumps(tombstone)
    return json.dumps({"status": "not_found", "message": f"No reminder matching: {title}"})


def search_reminders(query: str) -> str:
    """Search reminders by title or notes (case-insensitive). Includes both complete and incomplete."""
    q = query.lower()
    results = [
        r for r in store.list_reminders(include_deleted=False)
        if q in r["title"].lower() or q in (r.get("notes") or "").lower()
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
