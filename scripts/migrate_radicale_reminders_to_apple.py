#!/usr/bin/env python3
"""One-off migration: copy reminders from the old Radicale/CalDAV backend into the
new apple-reminders-server backend (real Apple Reminders via EventKit on Malcolm).

Run once, on a machine with network access to both the old Radicale instance
(GATEWAY_RADICALE__* in the gateway's own .env) and the new apple-reminders-server
(GATEWAY_REMINDERS_SERVER__* — same .env, read via gateway.config.Config, same as
the server does).

Idempotent: Radicale UIDs are preserved as the new store's ids, so re-running just
no-ops on rows that haven't changed since (the store's LWW guard rejects an equal
updated_at as stale). VTODO parsing here is a trimmed copy of the field mapping the
old CalDAV-backed store.py used before this migration — see
docs/superpowers/specs/2026-07-19-radicale-contacts-reminders-design.md for the
original table. Not part of the gateway package - delete after use.

Usage:
    cd /opt/awfulwoman/gateway && uv run scripts/migrate_radicale_reminders_to_apple.py [--dry-run]
"""
from __future__ import annotations
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import caldav
from gateway.config import Config
from gateway.reminders import store

_GEO_RE = re.compile(r"^geo:(-?[\d.]+),(-?[\d.]+)(?:;u=(\d+))?$")


def _to_rfc3339(prop) -> str | None:
    if prop is None:
        return None
    dt = prop.dt if hasattr(prop, "dt") else prop
    if not isinstance(dt, datetime):
        return dt.isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_location(vtodo) -> dict | None:
    for alarm in vtodo.subcomponents:
        if alarm.name != "VALARM" or "PROXIMITY" not in alarm:
            continue
        vloc = next((s for s in alarm.subcomponents if s.name == "VLOCATION"), None)
        if vloc is None or "URL" not in vloc:
            continue
        m = _GEO_RE.match(str(vloc.get("url")))
        if not m:
            continue
        return {
            "name": str(alarm.get("description", "")),
            "lat": float(m.group(1)),
            "lon": float(m.group(2)),
            "radius_m": int(m.group(3)) if m.group(3) else 150,
            "trigger": "arrive" if str(alarm.get("proximity")).upper() == "ARRIVE" else "leave",
        }
    return None


def _todo_to_reminder(todo: caldav.Todo) -> dict:
    vtodo = todo.icalendar_component
    status = str(vtodo.get("status", "NEEDS-ACTION"))
    updated_at = vtodo.get("x-gateway-updated-at")
    created_at = _to_rfc3339(vtodo.get("created")) or _to_rfc3339(vtodo.get("dtstamp")) or store.now_utc()
    return {
        "id": str(vtodo.get("uid", "")),
        "title": str(vtodo.get("summary", "")),
        "notes": str(vtodo.get("description")) if vtodo.get("description") is not None else None,
        "due": _to_rfc3339(vtodo.get("due")),
        "priority": int(vtodo.get("priority") or 0),
        "list": todo.parent.get_display_name() if todo.parent else "Reminders",
        "done": status == "COMPLETED",
        "completed_at": _to_rfc3339(vtodo.get("completed")),
        "created_at": created_at,
        "updated_at": str(updated_at) if updated_at is not None else created_at,
        "deleted": status == "CANCELLED",
        "location": _parse_location(vtodo),
    }


def _fetch_old_reminders(config) -> list[dict]:
    client = caldav.DAVClient(url=config.radicale.base_url, username=config.radicale.username, password=config.radicale.password)
    principal = client.principal()
    collections = [c for c in principal.calendars() if "VTODO" in c.get_supported_components()]
    reminders = []
    for c in collections:
        for todo in c.todos(include_completed=True):
            reminders.append(_todo_to_reminder(todo))
    return reminders


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    config = Config()
    assert config.radicale.base_url, "GATEWAY_RADICALE__BASE_URL required (source)"
    assert config.reminders_server.base_url, "GATEWAY_REMINDERS_SERVER__BASE_URL required (target)"
    store.init(config.reminders_server)

    reminders = _fetch_old_reminders(config)

    migrated = skipped_stale = skipped_bad = 0
    for reminder in reminders:
        if dry_run:
            print(f"  would migrate: {reminder['title']!r} (list={reminder['list']!r})")
            migrated += 1
            continue
        try:
            store.upsert(reminder)
            migrated += 1
        except store.Stale:
            skipped_stale += 1
        except ValueError as e:
            print(f"  skipping {reminder.get('title')!r}: {e}")
            skipped_bad += 1

    label = "Would migrate" if dry_run else "Migrated"
    print(f"\n{label} {migrated} reminders.")
    if skipped_stale:
        print(f"  {skipped_stale} already migrated at this or a newer updated_at.")
    if skipped_bad:
        print(f"  {skipped_bad} row(s) skipped (validation failure).")


if __name__ == "__main__":
    main()
