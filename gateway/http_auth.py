from __future__ import annotations
import hmac
import json
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Gates a path prefix behind `Authorization: Bearer <token>`. A no-op when
    `tokens` is empty, so shipping this before any token is configured changes
    nothing — enforcement only turns on once GATEWAY_SERVER__AUTH_TOKENS is set."""

    def __init__(self, app: ASGIApp, tokens: list[str], protect_prefix: str = "/mcp"):
        self._app = app
        self._tokens = tokens
        self._prefix = protect_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._tokens or not scope["path"].startswith(self._prefix):
            await self._app(scope, receive, send)
            return
        if not self._authorized(scope):
            await self._send_401(send)
            return
        await self._app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        headers = dict(scope["headers"])
        header = headers.get(b"authorization", b"").decode("latin-1")
        if not header.startswith("Bearer "):
            return False
        token = header[len("Bearer "):]
        return any(hmac.compare_digest(token, t) for t in self._tokens)

    async def _send_401(self, send: Send) -> None:
        body = json.dumps({"error": {"code": "unauthorized", "message": "missing or invalid bearer token"}}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})
