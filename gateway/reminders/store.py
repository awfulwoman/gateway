from __future__ import annotations
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
import caldav
from icalendar import Alarm, Todo as ICalTodo, vUri
from icalendar.cal import Component
from gateway.config import RadicaleConfig

_config: RadicaleConfig | None = None
_client_cache: caldav.DAVClient | None = None

_KNOWN_KEYS = {
    "id", "title", "notes", "due", "priority", "list", "done", "completed_at",
    "location", "created_at", "updated_at", "deleted",
}

# RFC 9074 requires a TRIGGER on a proximity VALARM even though it's ignored.
_PROXIMITY_TRIGGER_DUMMY = datetime(1976, 4, 1, 0, 55, 45, tzinfo=timezone.utc)
_GEO_RE = re.compile(r"^geo:(-?[\d.]+),(-?[\d.]+)(?:;u=(\d+))?$")


class Stale(Exception):
    def __init__(self, current: dict):
        super().__init__(f"stale write for reminder {current.get('id')!r}")
        self.current = current


def init(config: RadicaleConfig) -> None:
    global _config, _client_cache
    _config = config
    _client_cache = None


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_after(previous: str) -> str:
    """A timestamp strictly after `previous`: now_utc() if the wall clock has already
    moved past it, else `previous` + 1 second. Local writers minting a fresh
    updated_at for an edit should use this instead of bare now_utc() — two edits to
    the same reminder within one wall-clock second would otherwise collide and the
    second (legitimately later) one would be spuriously rejected by upsert's LWW
    guard, which correctly treats an equal updated_at as stale."""
    now = now_utc()
    if now > previous:
        return now
    dt = datetime.strptime(previous, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (dt + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return str(uuid.uuid4())


def _client() -> caldav.DAVClient:
    global _client_cache
    if _client_cache is None:
        assert _config and _config.base_url, "Radicale not configured (GATEWAY_RADICALE__BASE_URL required)"
        _client_cache = caldav.DAVClient(
            url=_config.base_url,
            username=_config.username,
            password=_config.password,
        )
    return _client_cache


def _todo_collections() -> list[caldav.Calendar]:
    principal = _client().principal()
    return [c for c in principal.calendars() if "VTODO" in c.get_supported_components()]


def _get_or_create_collection(list_name: str) -> caldav.Calendar:
    name = list_name or (_config.default_list if _config else "Reminders")
    for c in _todo_collections():
        if c.get_display_name() == name:
            return c
    principal = _client().principal()
    return principal.make_calendar(name=name, supported_calendar_component_set=["VTODO"])


def _find_todo(id: str) -> caldav.Todo | None:
    for c in _todo_collections():
        try:
            return c.todo_by_uid(id)
        except caldav.error.NotFoundError:
            continue
    return None


def _to_rfc3339(prop) -> str | None:
    if prop is None:
        return None
    dt = prop.dt if hasattr(prop, "dt") else prop
    if not isinstance(dt, datetime):
        return dt.isoformat()  # a plain date: already YYYY-MM-DD
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_due(value: str) -> date | datetime:
    if len(value) == 10:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _parse_location(vtodo: ICalTodo) -> dict | None:
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


def _todo_to_dict(todo: caldav.Todo) -> dict:
    vtodo = todo.icalendar_component
    status = str(vtodo.get("status", "NEEDS-ACTION"))
    updated_at = vtodo.get("x-gateway-updated-at")
    created_at = _to_rfc3339(vtodo.get("created")) or _to_rfc3339(vtodo.get("dtstamp")) or now_utc()

    d: dict = {
        "id": str(vtodo.get("uid", "")),
        "title": str(vtodo.get("summary", "")),
        "notes": str(vtodo.get("description")) if vtodo.get("description") is not None else None,
        "due": _to_rfc3339(vtodo.get("due")),
        "priority": int(vtodo.get("priority") or 0),
        "list": todo.parent.get_display_name() if todo.parent else (_config.default_list if _config else "Reminders"),
        "done": status == "COMPLETED",
        "completed_at": _to_rfc3339(vtodo.get("completed")),
        "created_at": created_at,
        "updated_at": str(updated_at) if updated_at is not None else created_at,
        "deleted": status == "CANCELLED",
        "location": _parse_location(vtodo),
    }

    extra_prop = vtodo.get("x-gateway-extra")
    if extra_prop:
        for k, v in json.loads(str(extra_prop)).items():
            d.setdefault(k, v)
    return d


def _build_ical(reminder: dict) -> str:
    if not (reminder.get("title") or "").strip():
        raise ValueError("title is required and must be non-empty")
    loc = reminder.get("location")
    if loc is not None and (loc.get("lat") is None or loc.get("lon") is None):
        raise ValueError("location requires lat and lon")

    vtodo = ICalTodo()
    vtodo.add("uid", reminder["id"])
    vtodo.add("summary", reminder["title"])
    if reminder.get("notes"):
        vtodo.add("description", reminder["notes"])
    if reminder.get("due"):
        vtodo.add("due", _parse_due(reminder["due"]))
    vtodo.add("priority", reminder.get("priority") or 0)
    vtodo.add("status", "CANCELLED" if reminder.get("deleted") else ("COMPLETED" if reminder.get("done") else "NEEDS-ACTION"))
    if reminder.get("completed_at"):
        vtodo.add("completed", _parse_ts(reminder["completed_at"]))
    vtodo.add("created", _parse_ts(reminder.get("created_at") or reminder["updated_at"]))
    vtodo.add("dtstamp", datetime.now(timezone.utc))
    vtodo["X-GATEWAY-UPDATED-AT"] = reminder["updated_at"]

    if loc is not None:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", loc.get("name") or reminder["title"])
        alarm.add("trigger", _PROXIMITY_TRIGGER_DUMMY, parameters={"VALUE": "DATE-TIME"})
        alarm["PROXIMITY"] = "ARRIVE" if loc.get("trigger", "arrive") == "arrive" else "DEPART"
        vloc = Component()
        vloc.name = "VLOCATION"
        vloc.add("url", vUri(f"geo:{loc['lat']},{loc['lon']};u={loc.get('radius_m', 150)}"))
        alarm.add_component(vloc)
        vtodo.add_component(alarm)

    extra = {k: v for k, v in reminder.items() if k not in _KNOWN_KEYS}
    if extra:
        vtodo["X-GATEWAY-EXTRA"] = json.dumps(extra)

    return vtodo.to_ical().decode("utf-8")


def get(id: str) -> dict | None:
    todo = _find_todo(id)
    return _todo_to_dict(todo) if todo is not None else None


def list_reminders(since: str | None = None, include_deleted: bool = True, list_name: str | None = None) -> list[dict]:
    if list_name:
        collections = [c for c in _todo_collections() if c.get_display_name() == list_name]
    else:
        collections = _todo_collections()

    results = []
    for c in collections:
        for todo in c.todos(include_completed=True):
            results.append(_todo_to_dict(todo))

    if since:
        results = [r for r in results if r["updated_at"] > since]
    if not include_deleted:
        results = [r for r in results if not r["deleted"]]
    results.sort(key=lambda r: r["updated_at"])
    return results


def upsert(reminder: dict) -> dict:
    if not (reminder.get("title") or "").strip():
        raise ValueError("title is required and must be non-empty")
    loc = reminder.get("location")
    if loc is not None and (loc.get("lat") is None or loc.get("lon") is None):
        raise ValueError("location requires lat and lon")

    existing_todo = _find_todo(reminder["id"])
    existing = _todo_to_dict(existing_todo) if existing_todo is not None else None
    if existing is not None and reminder["updated_at"] <= existing["updated_at"]:
        raise Stale(existing)

    ical = _build_ical(reminder)
    target_list = reminder.get("list") or (_config.default_list if _config else "Reminders")

    if existing_todo is not None and existing["list"] == target_list:
        existing_todo.icalendar_component = ICalTodo.from_ical(ical)
        existing_todo.save()
        return _todo_to_dict(existing_todo)

    # New reminder, or its list changed — CalDAV has no atomic move, so re-home it:
    # write to the target collection, then remove any prior copy elsewhere.
    collection = _get_or_create_collection(target_list)
    if existing_todo is not None:
        existing_todo.delete()
    saved = collection.add_todo(ical=ical)
    return _todo_to_dict(saved)


def soft_delete(id: str, updated_at: str | None = None) -> dict:
    existing = get(id)
    if existing is None:
        raise KeyError(f"no reminder with id {id!r}")
    tombstone = dict(existing)
    tombstone["deleted"] = True
    tombstone["updated_at"] = updated_at or now_after(existing["updated_at"])
    return upsert(tombstone)


def gc_tombstones(older_than_days: int = 30) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    removed = 0
    for c in _todo_collections():
        for todo in c.todos(include_completed=True):
            d = _todo_to_dict(todo)
            if d["deleted"] and d["updated_at"] < cutoff:
                todo.delete()
                removed += 1
    return removed
