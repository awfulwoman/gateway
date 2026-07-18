#!/usr/bin/env python3
"""One-off migration: copy reminders from the (retired) Radicale/CalDAV backend
into Gateway's own SQLite store.

Run this once, on the machine where the gateway server runs. Reads
GATEWAY_REMINDERS__* from the gateway's own .env file (via gateway.config.Config)
for both the old Radicale creds (base_url/username/password) and the new store
(db_path) and geocoder (nominatim_url) — same as the server does.

Idempotent: CalDAV UIDs are preserved as the SQLite id, so re-running just no-ops
on rows that haven't changed since (the store's LWW guard rejects an equal
updated_at as stale). Not part of the gateway package - delete after use.

Usage:
    cd /opt/awfulwoman/gateway && uv run scripts/migrate_radicale_to_sqlite.py [--dry-run]
"""
from __future__ import annotations
import os
import re
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import caldav
from gateway.config import Config
from gateway.reminders import geocode, store

_LOCATION_MARKER = re.compile(r"\[location:\s*(arrive|leave)\s+(.+?)\]\s*$", re.IGNORECASE | re.MULTILINE)


def _to_rfc3339(dt: date | datetime | None) -> str | None:
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return dt.isoformat()  # a plain date: already YYYY-MM-DD
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_location(notes: str) -> tuple[str, str | None, str]:
    """Split the old `[location: <arrive|leave> <name>]` marker out of notes.
    Returns (clean_notes, place_name_or_None, trigger)."""
    match = _LOCATION_MARKER.search(notes or "")
    if not match:
        return notes, None, "arrive"
    trigger, name = match.group(1).lower(), match.group(2).strip()
    clean_notes = _LOCATION_MARKER.sub("", notes).strip()
    return clean_notes, name, trigger


def _todo_to_reminder(todo) -> dict:
    vtodo = todo.icalendar_component
    uid = str(vtodo.get("uid", "")) or store.new_id()
    done = str(vtodo.get("status", "NEEDS-ACTION")) == "COMPLETED"

    notes, place_name, trigger = _extract_location(str(vtodo.get("description", "")))

    due_prop = vtodo.get("due")
    completed_prop = vtodo.get("completed")
    dtstamp_prop = vtodo.get("dtstamp")
    created_at = _to_rfc3339(dtstamp_prop.dt) if dtstamp_prop else store.now_utc()

    return {
        "id": uid,
        "title": str(vtodo.get("summary", "")),
        "notes": notes or None,
        "due": _to_rfc3339(due_prop.dt) if due_prop else None,
        "priority": int(vtodo.get("priority") or 0),
        "list": str(todo.parent.name) if todo.parent else "Reminders",
        "done": done,
        "completed_at": _to_rfc3339(completed_prop.dt) if completed_prop else None,
        "location": None,  # resolved by the caller, which has the geocode result
        "created_at": created_at,
        "updated_at": created_at,
        "deleted": False,
        "_place_name": place_name,
        "_trigger": trigger,
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    config = Config()
    assert config.reminders.base_url, "GATEWAY_REMINDERS__BASE_URL required (old Radicale creds)"
    store.init(config.reminders)
    geocode.init(config.reminders)

    client = caldav.DAVClient(
        url=config.reminders.base_url,
        username=config.reminders.username,
        password=config.reminders.password,
    )
    principal = client.principal()
    calendars = [c for c in principal.calendars() if "VTODO" in c.get_supported_components()]

    total = located = failed_geocodes = skipped_bad_rows = 0

    for cal in calendars:
        for todo in cal.get_todos(include_completed=True):
            reminder = _todo_to_reminder(todo)
            place_name, trigger = reminder.pop("_place_name"), reminder.pop("_trigger")

            if place_name:
                resolved = geocode.forward(place_name)
                if resolved:
                    reminder["location"] = {
                        "name": resolved["name"], "lat": resolved["lat"], "lon": resolved["lon"],
                        "radius_m": 150, "trigger": trigger,
                    }
                    located += 1
                else:
                    print(f"  could not geocode {place_name!r} for {reminder['title']!r}, skipping geofence")
                    failed_geocodes += 1

            total += 1
            if dry_run:
                continue
            try:
                store.upsert(reminder)
            except store.Stale:
                pass  # already migrated at this or a newer updated_at
            except ValueError as e:
                print(f"  skipping {reminder.get('title')!r}: {e}")
                skipped_bad_rows += 1

    label = "Would migrate" if dry_run else "Migrated"
    print(f"\n{label} {total} reminders ({located} with a resolved location).")
    if failed_geocodes:
        print(f"  {failed_geocodes} location(s) could not be geocoded (geofence skipped).")
    if skipped_bad_rows:
        print(f"  {skipped_bad_rows} row(s) skipped (validation failure).")


if __name__ == "__main__":
    main()
