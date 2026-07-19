#!/usr/bin/env python3
"""One-off migration: copy reminders from the old Gateway SQLite store into
Radicale via the new CalDAV-backed store.

Run once, on a machine with access to both the old SQLite reminders.db file and the
target Radicale instance (GATEWAY_RADICALE__* in the gateway's own .env, read via
gateway.config.Config — same as the server does).

Idempotent: SQLite row ids are preserved as CalDAV UIDs, so re-running just no-ops
on rows that haven't changed since (the store's LWW guard rejects an equal
updated_at as stale). Not part of the gateway package - delete after use.

Usage:
    cd /opt/awfulwoman/gateway && uv run scripts/migrate_sqlite_to_radicale.py <path-to-reminders.db> [--dry-run]
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway.config import Config
from gateway.reminders import store


def _row_to_reminder(row: sqlite3.Row) -> dict:
    d = {
        "id": row["id"],
        "title": row["title"],
        "notes": row["notes"],
        "due": row["due"],
        "priority": row["priority"],
        "list": row["list"],
        "done": bool(row["done"]),
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted": bool(row["deleted"]),
    }
    if row["loc_lat"] is not None:
        d["location"] = {
            "name": row["loc_name"],
            "lat": row["loc_lat"],
            "lon": row["loc_lon"],
            "radius_m": row["loc_radius_m"],
            "trigger": row["loc_trigger"],
        }
    else:
        d["location"] = None
    if row["extra"]:
        for k, v in json.loads(row["extra"]).items():
            d.setdefault(k, v)
    return d


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print("Usage: migrate_sqlite_to_radicale.py <path-to-reminders.db> [--dry-run]")
        sys.exit(1)
    db_path = args[0]

    config = Config()
    assert config.radicale.base_url, "GATEWAY_RADICALE__BASE_URL required"
    store.init(config.radicale)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM reminders").fetchall()

    migrated = skipped_stale = skipped_bad = 0
    for row in rows:
        reminder = _row_to_reminder(row)
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
