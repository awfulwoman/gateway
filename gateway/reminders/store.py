from __future__ import annotations
from datetime import datetime, timedelta, timezone
import uuid
import httpx
from gateway.config import RemindersServerConfig

_config: RemindersServerConfig | None = None
_client: httpx.Client | None = None


class Stale(Exception):
    def __init__(self, current: dict):
        super().__init__(f"stale write for reminder {current.get('id')!r}")
        self.current = current


def init(config: RemindersServerConfig) -> None:
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


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text


def get(id: str) -> dict | None:
    resp = _client.get(f"/reminders/{id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_reminders(since: str | None = None, include_deleted: bool = True, list_name: str | None = None) -> list[dict]:
    params = {}
    if since:
        params["since"] = since
    if list_name:
        params["list"] = list_name
    resp = _client.get("/reminders", params=params)
    resp.raise_for_status()
    results = resp.json()["reminders"]
    if not include_deleted:
        results = [r for r in results if not r["deleted"]]
    return results


def upsert(reminder: dict) -> dict:
    resp = _client.put(f"/reminders/{reminder['id']}", json=reminder)
    if resp.status_code == 409:
        raise Stale(resp.json()["current"])
    if resp.status_code == 400:
        raise ValueError(_error_message(resp))
    resp.raise_for_status()
    return resp.json()


def soft_delete(id: str, updated_at: str | None = None) -> dict:
    body = {"updated_at": updated_at} if updated_at else None
    resp = _client.request("DELETE", f"/reminders/{id}", json=body)
    if resp.status_code == 404:
        raise KeyError(f"no reminder with id {id!r}")
    if resp.status_code == 409:
        raise Stale(resp.json()["current"])
    resp.raise_for_status()
    return resp.json()


def gc_tombstones(older_than_days: int = 30) -> int:
    resp = _client.post("/admin/gc_tombstones", json={"older_than_days": older_than_days})
    resp.raise_for_status()
    return resp.json()["removed"]
