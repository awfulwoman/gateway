from __future__ import annotations
import json
from starlette.types import ASGIApp, Receive, Scope, Send
from gateway.auth import Client, parse_clients, resolve


class BearerAuthMiddleware:
    """Gates a path prefix behind `Authorization: Bearer <token>`. A no-op when
    `clients` is empty, so shipping this before any token is configured changes
    nothing — enforcement only turns on once GATEWAY_SERVER__AUTH_TOKENS is set.

    `clients` may be a list of `Client` or a list of raw token strings (bare
    secret or `label:secret`); strings are parsed with `auth.parse_clients`."""

    def __init__(self, app: ASGIApp, clients: list[Client] | list[str], protect_prefix: str = "/mcp"):
        self._app = app
        self._clients = _coerce(clients)
        self._prefix = protect_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._clients or not scope["path"].startswith(self._prefix):
            await self._app(scope, receive, send)
            return
        if self._resolve(scope) is None:
            await self._send_401(send)
            return
        await self._app(scope, receive, send)

    def _resolve(self, scope: Scope) -> Client | None:
        headers = dict(scope["headers"])
        header = headers.get(b"authorization", b"").decode("latin-1")
        return resolve(header, self._clients)

    async def _send_401(self, send: Send) -> None:
        body = json.dumps({"error": {"code": "unauthorized", "message": "missing or invalid bearer token"}}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})


def _coerce(clients: list[Client] | list[str]) -> list[Client]:
    if all(isinstance(c, Client) for c in clients):
        return list(clients)
    return parse_clients([c for c in clients if isinstance(c, str)])
