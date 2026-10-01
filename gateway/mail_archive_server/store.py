from __future__ import annotations
import httpx
from gateway.config import MailArchiveServerConfig

_config: MailArchiveServerConfig | None = None
_client: httpx.Client | None = None


class MailArchiveError(Exception):
    pass


def init(config: MailArchiveServerConfig) -> None:
    global _config, _client
    _config = config
    _client = httpx.Client(
        base_url=config.base_url,
        headers={"Authorization": f"Bearer {config.bearer_token}"},
        timeout=10.0,
    )


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text


def _params(**kwargs) -> dict:
    """Drops None values and renders bools the way the archive's query
    parsing expects (a bare "true"/"false" string, not Python's True/False).
    """
    out = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = value
    return out


def search(
    *, account: list[str] | None = None, q: str | None = None, from_: str | None = None,
    to: str | None = None, subject: str | None = None, since: str | None = None,
    until: str | None = None, seen: bool | None = None, has_attachment: bool | None = None,
    order: str | None = None, cursor: str | None = None, limit: int | None = None,
) -> dict:
    """Raises MailArchiveError on anything but 200 -- no IMAP credentials to
    fall back to (handoff spec §0), so an unreachable or erroring archive is
    a clear error, never a silently empty result.
    """
    params = _params(
        account=account, q=q, **{"from": from_}, subject=subject, since=since, until=until,
        seen=seen, has_attachment=has_attachment, order=order, cursor=cursor, limit=limit,
    )
    try:
        resp = _client.get("/messages", params=params)
    except httpx.HTTPError as exc:
        raise MailArchiveError(f"could not reach mail-archive-server: {exc}") from exc
    if resp.status_code != 200:
        raise MailArchiveError(_error_message(resp))
    return resp.json()


def get_message(id: str) -> dict | None:
    try:
        resp = _client.get(f"/messages/{id}")
    except httpx.HTTPError as exc:
        raise MailArchiveError(f"could not reach mail-archive-server: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise MailArchiveError(_error_message(resp))
    return resp.json()


def mark_read(id: str) -> dict:
    try:
        resp = _client.post(f"/messages/{id}/read")
    except httpx.HTTPError as exc:
        raise MailArchiveError(f"could not reach mail-archive-server: {exc}") from exc
    if resp.status_code != 200:
        raise MailArchiveError(_error_message(resp))
    return resp.json()


def accounts() -> list[dict]:
    try:
        resp = _client.get("/accounts")
    except httpx.HTTPError as exc:
        raise MailArchiveError(f"could not reach mail-archive-server: {exc}") from exc
    if resp.status_code != 200:
        raise MailArchiveError(_error_message(resp))
    return resp.json()["accounts"]


def sync(account: str | None = None) -> None:
    params = _params(account=account)
    try:
        resp = _client.post("/sync", params=params)
    except httpx.HTTPError as exc:
        raise MailArchiveError(f"could not reach mail-archive-server: {exc}") from exc
    if resp.status_code != 202:
        raise MailArchiveError(_error_message(resp))
