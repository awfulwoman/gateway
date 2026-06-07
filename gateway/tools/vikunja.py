from __future__ import annotations
import json
import httpx
from gateway.config import VikunjaConfig

_config: VikunjaConfig | None = None


def init(config: VikunjaConfig) -> None:
    global _config
    _config = config


def _client() -> httpx.Client:
    assert _config and _config.base_url and _config.api_token, (
        "Vikunja not configured (GATEWAY_VIKUNJA__BASE_URL and GATEWAY_VIKUNJA__API_TOKEN required)"
    )
    return httpx.Client(
        base_url=f"{_config.base_url.rstrip('/')}/api/v1",
        headers={
            "Authorization": f"Bearer {_config.api_token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )


def register(mcp) -> None:
    for fn in []:
        mcp.tool()(fn)
