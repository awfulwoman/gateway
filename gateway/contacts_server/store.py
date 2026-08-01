from __future__ import annotations
import uuid
import httpx
from gateway.config import ContactsServerConfig

_config: ContactsServerConfig | None = None
_client: httpx.Client | None = None


def init(config: ContactsServerConfig) -> None:
    global _config, _client
    _config = config
    _client = httpx.Client(
        base_url=config.base_url,
        headers={"Authorization": f"Bearer {config.bearer_token}"},
        timeout=10.0,
    )


def new_id() -> str:
    return str(uuid.uuid4())


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text


def get(id: str) -> dict | None:
    resp = _client.get(f"/contacts/{id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_contacts() -> list[dict]:
    resp = _client.get("/contacts")
    resp.raise_for_status()
    return resp.json()["contacts"]


def upsert(contact: dict) -> dict:
    resp = _client.put(f"/contacts/{contact['id']}", json=contact)
    if resp.status_code == 400:
        raise ValueError(_error_message(resp))
    resp.raise_for_status()
    return resp.json()


def delete(id: str) -> bool:
    resp = _client.delete(f"/contacts/{id}")
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True
