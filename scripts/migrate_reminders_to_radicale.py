#!/usr/bin/env python3
"""One-off migration: copy existing Apple Reminders (via EventKit) into Radicale.

Run this once, on the machine where EventKit already has Reminders access
(the one gateway currently runs on), pointed at the deployed Radicale
instance. Not part of the gateway package - delete after use.

Usage:
    GATEWAY_REMINDERS__BASE_URL=https://radicale.example.com \\
    GATEWAY_REMINDERS__USERNAME=charlie \\
    GATEWAY_REMINDERS__PASSWORD=... \\
    uv run scripts/migrate_reminders_to_radicale.py [--dry-run]
"""
from __future__ import annotations
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway.config import RemindersConfig
from gateway.tools import reminders


def _fetch_apple_reminders() -> list[dict]:
    import EventKit

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def grant_cb(granted, error):
        done.set()

    try:
        store.requestFullAccessToRemindersWithCompletion_(grant_cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeReminder, grant_cb)
    done.wait(timeout=10)

    pred = store.predicateForRemindersInCalendars_(None)
    found: list = []
    fetch_done = threading.Event()

    def fetch_cb(items):
        found.extend(items or [])
        fetch_done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, fetch_cb)
    fetch_done.wait(timeout=10)

    results = []
    for r in found:
        due = None
        if r.dueDateComponents():
            dc = r.dueDateComponents()
            try:
                due = f"{dc.year():04d}-{dc.month():02d}-{dc.day():02d}"
            except Exception:
                due = None
        results.append({
            "title": str(r.title() or ""),
            "completed": bool(r.isCompleted()),
            "due": due,
            "notes": str(r.notes() or ""),
            "priority": int(r.priority()),
            "list": str(r.calendar().title() or "Reminders"),
        })
    return results


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    config = RemindersConfig(
        base_url=os.environ["GATEWAY_REMINDERS__BASE_URL"],
        username=os.environ["GATEWAY_REMINDERS__USERNAME"],
        password=os.environ["GATEWAY_REMINDERS__PASSWORD"],
    )
    reminders.init(config)

    items = _fetch_apple_reminders()
    print(f"Found {len(items)} reminders in Apple Reminders.")

    by_list: dict[str, int] = {}
    for item in items:
        by_list[item["list"]] = by_list.get(item["list"], 0) + 1
    for list_name, count in by_list.items():
        print(f"  {list_name}: {count}")

    if dry_run:
        print("\n--dry-run set, not writing to Radicale.")
        return

    existing = {cal.name for cal in reminders._todo_calendars()}
    principal = reminders._get_client().principal()
    for list_name in by_list:
        if list_name not in existing:
            print(f"Creating list on Radicale: {list_name}")
            principal.make_calendar(name=list_name, supported_calendar_component_set=["VTODO"])

    created = 0
    for item in items:
        reminders.create_reminder(
            title=item["title"],
            due_iso=item["due"] or "",
            notes=item["notes"],
            list_name=item["list"],
            priority=item["priority"],
        )
        created += 1
        if item["completed"]:
            reminders.complete_reminder(item["title"])

    print(f"\nMigrated {created} reminders into Radicale.")


if __name__ == "__main__":
    main()
