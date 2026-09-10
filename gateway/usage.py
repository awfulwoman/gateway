from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from gateway.auth import Client, client_ip, resolve

logger = logging.getLogger("gateway.usage")

_PREFIX = "/mcp"
_MAX_BODY = 256 * 1024  # only parse this much for logging; the full body is still replayed


class UsageLogMiddleware:
    """Emits one structured JSON line per `/mcp` request: who called (bearer-token
    label), the JSON-RPC method and — for `tools/call` — the tool name and its
    full arguments, plus response status and duration. Non-`/mcp` requests pass
    straight through with no buffering and no logging."""

    def __init__(self, app: ASGIApp, clients: list[Client]):
        self._app = app
        self._clients = clients

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(_PREFIX):
            await self._app(scope, receive, send)
            return

        body, replay = await _buffer_body(receive)

        status: dict = {"code": None}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        started = time.monotonic()
        try:
            await self._app(scope, replay, send_wrapper)
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 1)
            try:
                self._emit(scope, body, status["code"], duration_ms)
            except Exception:  # logging must never break a request
                logger.exception("usage logging failed")

    def _emit(self, scope: Scope, body: bytes, status: int | None, duration_ms: float) -> None:
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization", b"").decode("latin-1")
        matched = resolve(auth_header, self._clients)
        base = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "caller": matched.label if matched else None,
            "ip": client_ip(scope),
            "ua": headers.get(b"user-agent", b"").decode("latin-1") or None,
            "status": status,
            "duration_ms": duration_ms,
        }
        for call in _rpc_calls(body):
            logger.info(json.dumps({**base, **call}, default=str))


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    """Drain the request body, then hand back a fresh `receive` that replays it."""
    chunks: list[bytes] = []
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            # e.g. http.disconnect before the body finished; stop draining.
            chunks_left = [message]
            break
        chunks.append(message.get("body", b""))
        more = message.get("more_body", False)
    else:
        chunks_left = []

    body = b"".join(chunks)
    queue = list(chunks_left)
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    return body, replay


def _rpc_calls(body: bytes) -> list[dict]:
    """One dict of {method, tool, args, rpc_id} per JSON-RPC call in the body.
    Falls back to a single method=None entry when the body is absent or not
    JSON-RPC (GET stream opens, malformed payloads)."""
    if not body:
        return [{"method": None, "tool": None, "args": None, "rpc_id": None}]
    try:
        payload = json.loads(body[:_MAX_BODY])
    except (ValueError, UnicodeDecodeError):
        return [{"method": None, "tool": None, "args": None, "rpc_id": None}]

    items = payload if isinstance(payload, list) else [payload]
    calls: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        method = item.get("method")
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        tool = params.get("name") if method == "tools/call" else None
        args = params.get("arguments") if method == "tools/call" else None
        calls.append({"method": method, "tool": tool, "args": args, "rpc_id": item.get("id")})
    return calls or [{"method": None, "tool": None, "args": None, "rpc_id": None}]
