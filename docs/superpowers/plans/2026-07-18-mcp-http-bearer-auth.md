# MCP HTTP bearer auth — implementation plan

**Date:** 2026-07-18
**Status:** Proposed

## Context

Gateway's HTTP surface today has **no authentication**. `_run_http` in
`gateway/main.py` serves `mcp.streamable_http_app()` (the `/mcp` streamable-HTTP
endpoint) wrapped only in `_DisconnectMiddleware`. Any peer that can reach
`host:port` (default `127.0.0.1:4000`, but bound to a reachable interface on
malcolm) can call **every** MCP tool — read email, notes, contacts, location
history, create calendar events, etc.

This is acceptable *today* because Gateway is used by a single user on an isolated
network reached over a VPN. But "isolated network + VPN" is one misconfiguration
(a wrong bind address, a VPN split-tunnel leak, a future second host) away from an
open, unauthenticated tool server. Bearer auth is cheap defense-in-depth and makes
the trust boundary explicit rather than implicit-in-the-network.

The companion `/v1/reminders` API
(`docs/superpowers/plans/2026-07-18-reminders-json-interchange.md`) already adds
per-device bearer auth in its route handlers. This plan brings the **`/mcp`**
surface up to the same bar, so no HTTP endpoint on Gateway is unauthenticated.

**No new runtime deps** — a small ASGI middleware over `hmac.compare_digest`.

---

## Design

- A single ASGI **bearer-auth middleware** wraps the served app in `_run_http`,
  *outside* the existing `_DisconnectMiddleware`. It enforces on the `/mcp` path
  prefix only; `/v1/*` continues to authenticate in its own handlers (separate
  device-token list, separate revocation), and the middleware passes those through
  untouched.
- Tokens live in a new `ServerConfig.auth_tokens: list[str]` (comma-separated env
  var), mirroring the reminders `api_tokens` pattern — a **list** so each MCP
  client (laptop, phone-side tooling, a scratch token) can be revoked
  independently without rotating the others.
- Check: read `Authorization: Bearer <t>`; `hmac.compare_digest` against each
  configured token; on miss return `401` with the same `{"error": {...}}` body
  shape as `/v1`. Missing header → `401`.
- **`stdio` transport is unaffected** — it has no HTTP layer and is how Claude Code
  integrates directly; auth only exists on the `http` transport.

### Rollout safety (avoid locking yourself out)

Enforcement is **opt-in on presence of tokens**:

- `auth_tokens` empty ⇒ middleware allows all `/mcp` traffic but logs a loud
  startup **warning** ("MCP HTTP auth DISABLED — set GATEWAY_SERVER__AUTH_TOKENS").
  This keeps the current deploy working the instant the code lands.
- `auth_tokens` non-empty ⇒ enforced; unauthenticated `/mcp` calls get `401`.

So the cutover is: deploy code (still open, warns) → add the token to the client
registration → set `GATEWAY_SERVER__AUTH_TOKENS` and redeploy (now enforced).
Never a window where the client is updated but the server rejects it, or vice
versa.

---

## Part 1 — Config (`gateway/config.py`, `.env.example`)

The reminders plan already added a shared `_split_csv` helper to
`gateway/config.py` for its `api_tokens` field — reuse it:

```python
from typing import Annotated
from pydantic import field_validator
from pydantic_settings import NoDecode

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4000
    auth_tokens: Annotated[list[str], NoDecode] = []   # GATEWAY_SERVER__AUTH_TOKENS (comma-sep)

    @field_validator("auth_tokens", mode="before")
    @classmethod
    def _split(cls, v):
        return _split_csv(v)
```

**Gotcha (same as reminders `api_tokens`):** a bare `mode="before"` validator is
not enough — pydantic-settings' `EnvSettingsSource` tries to `json.loads()` a
`list[str]` env var before any validator runs, so a plain comma-string raises
`SettingsError` at `Config()` construction. `Annotated[list[str], NoDecode]` skips
that pre-decode and lets the validator see the raw string. Verified against
pydantic-settings 2.14.0 while implementing the reminders store
(`tests/test_config.py`).

`.env.example`: add
`GATEWAY_SERVER__AUTH_TOKENS=laptop-mcp-token,scratch-token` with a comment that
empty = auth disabled.

## Part 2 — Middleware (`gateway/http_auth.py`, new)

A tiny reusable ASGI middleware so `/mcp` (and, if ever wanted, other surfaces)
share one implementation:

```python
import hmac
from starlette.types import ASGIApp, Scope, Receive, Send

class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, tokens: list[str], protect_prefix: str = "/mcp"):
        self._app = app
        self._tokens = tokens
        self._prefix = protect_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not self._tokens \
           or not scope["path"].startswith(self._prefix):
            await self._app(scope, receive, send)
            return
        if not self._authorized(scope):
            await self._send_401(send)
            return
        await self._app(scope, receive, send)
```

- `_authorized` — pull `authorization` from `scope["headers"]` (bytes, lowercase
  keys); require `Bearer `; `hmac.compare_digest` against each token; short-circuit
  false if none match.
- `_send_401` — send an ASGI `http.response.start` (status 401,
  `content-type: application/json`) + `http.response.body`
  `{"error": {"code": "unauthorized", "message": "..."}}`.
- Empty `tokens` ⇒ the guard is skipped entirely (open, per rollout above).

Unit-testable in isolation with a stub `app`/`send`.

## Part 3 — Wire into server (`gateway/main.py`)

```python
from gateway.http_auth import BearerAuthMiddleware

async def _run_http(mcp: FastMCP, config: Config) -> None:
    app = mcp.streamable_http_app()
    app.router.routes.extend(reminders_http.routes)     # from the reminders plan
    app = BearerAuthMiddleware(app, config.server.auth_tokens)  # /mcp guard
    app = _DisconnectMiddleware(app)
    ...
```

- Log the "auth DISABLED" warning at startup when `config.server.auth_tokens` is
  empty (do it in `create_server` or at the top of `_run_http`).
- `_run_http` needs `config` in scope — thread it through from `main()`
  (currently it only receives `mcp`). Trivial signature change.
- Order matters: `BearerAuthMiddleware` **inside** `_DisconnectMiddleware` is fine;
  it must sit **outside** the MCP app so it sees the request before FastMCP does.
- This composes cleanly with the reminders plan's Part 5 (both extend/wrap the same
  `app`); land whichever first and the other slots in.

## Part 4 — Client re-registration

The MCP is registered with `claude mcp add` (per the user's convention — never
hand-edit the JSON). Streamable-HTTP transport forwards custom headers, so re-add
Gateway with the bearer header:

```
claude mcp remove gateway
claude mcp add --transport http gateway <gateway-vpn-url>/mcp \
  --header "Authorization: Bearer <laptop-mcp-token>"
```

Do this for every place Gateway's MCP is registered (laptop, any other machine).
Keep each machine's token distinct so it can be revoked alone.

## Part 5 — Tests (`tests/test_http_auth.py`)

- Middleware with tokens set: no header → 401; `Bearer wrong` → 401;
  `Bearer <good>` → passes to inner app (stub asserts it was called).
- Middleware with **empty** tokens: any request passes through (open mode).
- Path scoping: a `/v1/...` request is passed through untouched even with a bad
  token (so `/v1` handler auth stays authoritative and there's no double-guard).
- Non-http scope (`lifespan`/`websocket`) passes through.

(Starlette `TestClient` against a minimal app mounting the middleware, or drive the
ASGI callable directly with a fake `send`.)

## Order of work

1. Part 1 config + validator.
2. Part 2 middleware + Part 5 tests → green.
3. Part 3 wiring in `main.py`; startup warning.
4. `uv run pytest`; deploy code (auth still open, warning logged).
5. Part 4: re-register the MCP client(s) with the header.
6. Set `GATEWAY_SERVER__AUTH_TOKENS` in the live `.env`, redeploy — now enforced.
   (`.claude/rules/deploy.md`.)

## Verification

- `uv run pytest`.
- Local server with `GATEWAY_SERVER__AUTH_TOKENS=test`:
  - `curl -sN localhost:4000/mcp -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'` **without** the bearer →
    `401`.
  - Same with `-H 'Authorization: Bearer test'` → normal MCP response.
  - `/v1/reminders` still governed by its own device token (bad server token but
    good reminders token → 200), confirming the surfaces are independent.
- With `GATEWAY_SERVER__AUTH_TOKENS` unset → `/mcp` works and the startup log shows
  the "auth DISABLED" warning.
- After live cutover: Claude Code's Gateway MCP tools work with the header
  configured; removing the header (or using a wrong token) makes them fail 401.

## Non-goals (this plan)

- OAuth / FastMCP's built-in `TokenVerifier` / scopes / per-tool authorization —
  a single shared-secret bearer is sufficient for one user. (FastMCP's OAuth path
  is the upgrade route if multi-user ever happens.)
- Rate limiting, audit logging, mTLS.
- Changing the `/v1` reminders auth (separate, already specified).
- Network-level controls (VPN, firewall, bind address) — those stay as they are;
  this is defense-in-depth *behind* them, not a replacement.
