from __future__ import annotations
from datetime import datetime, timedelta, timezone
import uuid
import httpx
from gateway.config import CalendarServerConfig

_config: CalendarServerConfig | None = None
_client: httpx.Client | None = None


class Stale(Exception):
    def __init__(self, current: dict):
        super().__init__(f"stale write for event {current.get('id')!r}")
        self.current = current


def init(config: CalendarServerConfig) -> None:
    global _config, _client
    _config = config
    _client = httpx.Client(
        base_url=config.base_url,
        headers={"Authorization": f"Bearer {config.bearer_token}"},
        timeout=10.0,
    )


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_after(previous: str) -> str:
    """A timestamp strictly after `previous`: now_utc() if the wall clock has already
    moved past it, else `previous` + 1 second. See gateway.reminders.store.now_after —
    identical rationale, avoids spurious LWW rejections on same-second edits."""
    now = now_utc()
    if now > previous:
        return now
    dt = datetime.strptime(previous, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (dt + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return str(uuid.uuid4())


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text


def get(id: str) -> dict | None:
    resp = _client.get(f"/events/{id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_events(
    start: str | None = None,
    end: str | None = None,
    calendar_name: str | None = None,
    since: str | None = None,
    include_deleted: bool = True,
) -> list[dict]:
    params = {}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    if calendar_name:
        params["calendar"] = calendar_name
    if since:
        params["since"] = since
    resp = _client.get("/events", params=params)
    resp.raise_for_status()
    results = resp.json()["events"]
    if not include_deleted:
        results = [e for e in results if not e["deleted"]]
    return results


def list_calendars() -> list[str]:
    resp = _client.get("/calendars")
    resp.raise_for_status()
    return resp.json()["calendars"]


def upsert(event: dict) -> dict:
    resp = _client.put(f"/events/{event['id']}", json=event)
    if resp.status_code == 409:
        raise Stale(resp.json()["current"])
    if resp.status_code == 400:
        raise ValueError(_error_message(resp))
    resp.raise_for_status()
    return resp.json()


def soft_delete(id: str, updated_at: str | None = None) -> dict:
    body = {"updated_at": updated_at} if updated_at else None
    resp = _client.request("DELETE", f"/events/{id}", json=body)
    if resp.status_code == 404:
        raise KeyError(f"no event with id {id!r}")
    if resp.status_code == 409:
        raise Stale(resp.json()["current"])
    resp.raise_for_status()
    return resp.json()


def gc_tombstones(older_than_days: int = 30) -> int:
    resp = _client.post("/admin/gc_tombstones", json={"older_than_days": older_than_days})
    resp.raise_for_status()
    return resp.json()["removed"]
