from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from gateway.config import RemindersConfig

_config: RemindersConfig | None = None
_conn_cache: sqlite3.Connection | None = None

_KNOWN_KEYS = {
    "id", "title", "notes", "due", "priority", "list", "done", "completed_at",
    "location", "created_at", "updated_at", "deleted",
}


class Stale(Exception):
    def __init__(self, current: dict):
        super().__init__(f"stale write for reminder {current.get('id')!r}")
        self.current = current


def init(config: RemindersConfig) -> None:
    global _config, _conn_cache
    _config = config
    _conn_cache = None


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return str(uuid.uuid4())


def _conn() -> sqlite3.Connection:
    global _conn_cache
    if _conn_cache is None:
        assert _config and _config.db_path, "Reminders store not configured (GATEWAY_REMINDERS__DB_PATH required)"
        path = Path(_config.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
              id           TEXT PRIMARY KEY,
              title        TEXT NOT NULL,
              notes        TEXT,
              due          TEXT,
              priority     INTEGER NOT NULL DEFAULT 0,
              list         TEXT NOT NULL DEFAULT 'Reminders',
              done         INTEGER NOT NULL DEFAULT 0,
              completed_at TEXT,
              loc_name     TEXT,
              loc_lat      REAL,
              loc_lon      REAL,
              loc_radius_m INTEGER,
              loc_trigger  TEXT,
              created_at   TEXT NOT NULL,
              updated_at   TEXT NOT NULL,
              deleted      INTEGER NOT NULL DEFAULT 0,
              extra        TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_updated_at ON reminders(updated_at)")
        conn.commit()
        _conn_cache = conn
    return _conn_cache


def _row_to_dict(row: sqlite3.Row) -> dict:
    d: dict = {
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


def _dict_to_params(d: dict) -> dict:
    loc = d.get("location") or {}
    extra = {k: v for k, v in d.items() if k not in _KNOWN_KEYS}
    return {
        "id": d["id"],
        "title": d["title"],
        "notes": d.get("notes"),
        "due": d.get("due"),
        "priority": d.get("priority") or 0,
        "list": d.get("list") or "Reminders",
        "done": 1 if d.get("done") else 0,
        "completed_at": d.get("completed_at"),
        "loc_name": loc.get("name"),
        "loc_lat": loc.get("lat"),
        "loc_lon": loc.get("lon"),
        "loc_radius_m": loc.get("radius_m"),
        "loc_trigger": loc.get("trigger"),
        "created_at": d["created_at"],
        "updated_at": d["updated_at"],
        "deleted": 1 if d.get("deleted") else 0,
        "extra": json.dumps(extra) if extra else None,
    }


def get(id: str) -> dict | None:
    row = _conn().execute("SELECT * FROM reminders WHERE id = ?", (id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_reminders(since: str | None = None, include_deleted: bool = True, list_name: str | None = None) -> list[dict]:
    query = "SELECT * FROM reminders WHERE 1=1"
    params: list = []
    if since:
        query += " AND updated_at > ?"
        params.append(since)
    if not include_deleted:
        query += " AND deleted = 0"
    if list_name:
        query += " AND list = ?"
        params.append(list_name)
    query += " ORDER BY updated_at"
    rows = _conn().execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert(reminder: dict) -> dict:
    if not (reminder.get("title") or "").strip():
        raise ValueError("title is required and must be non-empty")
    loc = reminder.get("location")
    if loc is not None and (loc.get("lat") is None or loc.get("lon") is None):
        raise ValueError("location requires lat and lon")

    existing = get(reminder["id"])
    if existing is not None and reminder["updated_at"] <= existing["updated_at"]:
        raise Stale(existing)

    params = _dict_to_params(reminder)
    columns = list(params.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
    conn = _conn()
    conn.execute(
        f"INSERT INTO reminders ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        params,
    )
    conn.commit()
    return get(reminder["id"])


def soft_delete(id: str, updated_at: str | None = None) -> dict:
    existing = get(id)
    if existing is None:
        raise KeyError(f"no reminder with id {id!r}")
    tombstone = dict(existing)
    tombstone["deleted"] = True
    tombstone["updated_at"] = updated_at or now_utc()
    return upsert(tombstone)


def gc_tombstones(older_than_days: int = 30) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _conn()
    cur = conn.execute("DELETE FROM reminders WHERE deleted = 1 AND updated_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount
