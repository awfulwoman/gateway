# Gateway REST API (FastAPI) — Design Spec

**Date:** 2026-07-19
**Status:** Proposed
**Audience:** the developer adding a resource-oriented HTTP API to Gateway, alongside the
existing MCP server and `gw` CLI. Assumes familiarity with the tool pattern
(`init`/`register`, one module per source) and the existing `/v1/reminders` Starlette
routes.
Companion implementation plan: `docs/superpowers/plans/2026-07-19-rest-api.md` (to be
written after this spec is approved).

---

## 1. Why

Gateway exposes its tools two ways today, but only **one** of them is a general HTTP
surface, and neither suits a native app:

- **MCP** (`/mcp`) — JSON-RPC `tools/call` over streamable HTTP/SSE. Designed for LLM
  agents; the envelope (`result.content[0].text` holding a JSON *string*, SSE framing) is
  awkward for a plain HTTP client to consume.
- **`gw` CLI** — not a separate backend at all: `gateway/cli/client.py` is just an HTTP
  client of `/mcp`.
- **`/v1/reminders`** (`gateway/reminders/http.py`) — the one hand-written,
  resource-style REST surface, built specifically because a native iOS app needed clean
  JSON-over-HTTPS with offline sync.

We want a **first-class REST API** covering the rest of the tool surface, so a remote
iOS app — and any future client — can talk to Gateway idiomatically. This generalises
the pattern that `/v1/reminders` already proved.

**Target end-state layering.** Two thin adapters over one set of tool functions:

- **MCP (`/mcp`)** — the adapter for **LLM agents** (Claude Code, `chives`).
- **REST (`/v1/*`)** — the adapter for **programmatic clients**: the iOS app, the `gw`
  CLI, and anything future.

Today the CLI is oddly a client of the *MCP* surface despite not being an agent. Part of
this effort's direction is to fix that: **the CLI will migrate to the REST API**, so MCP
is left as agents-only. That migration is **not** in v1 — see the Non-goals below and the
detailed plan in §9 — but the API is designed from the start to be the CLI's eventual
backend.

### Goals

- Idiomatic, resource-oriented REST under `/v1/*` (e.g. `GET /v1/bookmarks`), returning
  plain typed JSON — no MCP/JSON-RPC envelope.
- **Per-client bearer tokens with scopes** so a remote client gets least-privilege access
  (a token can be limited to, say, `bookmarks:read` + `email:read`).
- **Self-describing**: OpenAPI at `/v1/openapi.json` and interactive docs at `/v1/docs`.
- **Reuse, not re-implement**: routers call the existing tool functions
  (`karakeep.*`, `email.*`); the API layer only re-shapes HTTP ergonomics (routing,
  validation, response models), never re-implements a backend integration.
- Additive and non-breaking: MCP, the CLI, and the existing `/v1/reminders`+`/v1/geocode`
  routes are untouched.

### Non-goals (v1)

- No new domains beyond **Bookmarks** (Karakeep) and **Email** (IMAP) in this first
  version. Calendar, Notes/Issues, Location follow later, same pattern.
- No change to the `/v1/reminders` offline-sync protocol or its auth — it's frozen and
  documented in its own spec. (Converging it onto this API's scoped auth is a listed
  follow-up, §9.)
- **Contacts is excluded** — it's macOS-only and absent from the Linux container
  (`sys.platform` gate; see the docker-deployment spec). No REST surface for it.
- No OAuth / user login / multi-user. One owner, static per-client tokens, exactly like
  every other Gateway secret.
- No websockets/streaming; request/response only.
- **The `gw` CLI is not migrated in v1** — it stays a pure MCP client. It moves to the
  REST API **wholesale**, in a single later change, only once the API covers its full
  command surface (§9). It is never a mixed MCP+REST client.

---

## 2. Decisions (locked with Charlie, 2026-07-19)

1. **Shape:** full resource-oriented REST (not a generic RPC passthrough).
2. **Foundation:** **FastAPI**, mounted in the same uvicorn process as MCP. Gives
   OpenAPI, pydantic validation, and scope-aware dependencies for near-free — pydantic
   is already a dependency; FastAPI is the only new runtime dep.
3. **Auth:** per-client named bearer tokens carrying **`domain:verb`** scopes, with
   wildcards.
4. **Discoverability:** generated OpenAPI + docs.
5. **First domains:** Bookmarks + Email.
6. **CLI migration:** the `gw` CLI will move from MCP to the REST API, but **wholesale and
   later** — it stays 100% MCP through v1 and switches in one change once the API covers
   its full surface (never a mixed-transport client). End state: MCP is agents-only.

---

## 3. Architecture

```
                         ┌───────────────────────── uvicorn (one process, :4000) ─────┐
   iOS app / clients     │                                                            │
   ── Bearer token ─────▶│  FastAPI app  (gateway/api/app.py)                         │
                         │    ├── /v1/bookmarks/*   router ─┐                         │
                         │    ├── /v1/emails/*      router ─┤ call existing tool fns  │
                         │    ├── /v1/folders       router ─┘  (karakeep.*, email.*)  │
                         │    ├── /v1/openapi.json, /v1/docs   (auto)                  │
                         │    │                                                        │
                         │    ├── /v1/reminders*, /v1/geocode  (existing Starlette     │
                         │    │        routes, carried over unchanged — own auth)      │
   Claude / gw CLI  ────▶│    └── /mcp   (FastMCP streamable app, mounted; own auth)   │
                         └────────────────────────────────────────────────────────────┘
```

- New package `gateway/api/`:
  - `app.py` — builds the FastAPI app: OpenAPI metadata + bearer security scheme,
    includes the routers, registers exception handlers, and composes the MCP app +
    legacy `/v1/reminders`/`/v1/geocode` routes.
  - `auth.py` — the scoped-token model + the `require(scope)` dependency.
  - `errors.py` — exception handlers rendering the shared error envelope.
  - `models.py` — pydantic request/response models per domain.
  - `routers/bookmarks.py`, `routers/email.py`.
- `main.py` `_run_http` changes from "MCP Starlette app + extend routes + middleware" to
  "build the composed FastAPI app, then serve it." The `--transport stdio` path is
  unaffected.

### 3.1 The composition risk: MCP lifespan (highest-risk item)

Making FastAPI the top-level app and putting MCP underneath it silently breaks `/mcp`
unless the lifespan is wired by hand. This is easy to fix but easy to ship broken, so it
is called out in full.

**How MCP boots today.** `mcp.streamable_http_app()` returns a Starlette app whose
**lifespan is what starts MCP**:

```python
# mcp/server/fastmcp/server.py — streamable_http_app()
return Starlette(..., lifespan=lambda app: self.session_manager.run())
```

`session_manager.run()` creates the anyio task group every request needs, logging the
`StreamableHTTP session manager started` line seen at boot. Every `/mcp` request enters
`StreamableHTTPSessionManager.handle_request()`, which begins:

```python
if self._task_group is None:
    raise RuntimeError("Task group is not initialized. Make sure to use run().")
```

So the task group exists **only if the app's lifespan ran**. Today it always runs,
because `mcp.streamable_http_app()` is the top-level app uvicorn serves directly.

**Why mounting breaks it.** ASGI has three scope types — `http`, `websocket`, and
`lifespan`. Uvicorn sends `lifespan` events to **exactly one** app: the top-level one.
Starlette `Mount` / FastAPI `.mount()` forward `http`/`websocket` scopes to sub-apps but
**do not forward `lifespan`** — a mounted app's `lifespan=` is never called. Result once
MCP is mounted under FastAPI:

- `session_manager.run()` never runs → `_task_group` stays `None`.
- FastAPI boots clean, `/v1/*` works, the healthcheck passes — everything *looks*
  healthy.
- The first real `/mcp` call 500s with `RuntimeError: Task group is not initialized`.
- The failure surfaces in a **different** client (Claude / `chives` / `gw`) than the one
  under test (the new REST endpoints), so manual testing of the API misses it entirely.

**The fix.** The parent FastAPI app owns a lifespan that drives the session manager
itself:

```python
mcp_app = mcp.streamable_http_app()          # side effect: lazily creates the session manager

@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():    # what the mounted app can no longer do for itself
        yield

app = FastAPI(lifespan=lifespan, ...)
```

**Two sharp edges the plan must respect:**

1. **`run()` is once-per-instance.** Its own guard raises
   `RuntimeError(".run() can only be called once per instance ...")`. Drive it in exactly
   one place (the parent lifespan). Do **not** also propagate the mounted app's lifespan
   "to be safe" — that double-runs it and crashes. (Mount dropping the child lifespan is
   the desired behaviour here, not a bug to work around.)
2. **The `/mcp` path prefix.** FastMCP's route sits at its `streamable_http_path`
   (default `/mcp`). `app.mount("/mcp", mcp_app)` yields `/mcp` + `/mcp` = `/mcp/mcp`.
   Either mount the raw `StreamableHTTPASGIApp` handler at `/mcp`, or set FastMCP's path
   to `/` and mount the sub-app at `/mcp`. The plan must pin one down and assert the final
   path in a test.

**Required regression test.** A test must exercise a real `tools/call` through the
**composed** app (via `TestClient` with lifespan enabled) and assert it succeeds — so a
green suite, not manual luck, proves `/mcp` survived the move. See §10.

**Reuse principle (why "full REST" isn't a third re-implementation):** the backend
integrations already live once, in the tool modules. A router handler validates input,
calls the existing tool function (e.g. `karakeep.search_bookmarks(query, limit, cursor)`),
`json.loads` its result, and returns it as a typed response model. The only new code is
HTTP shape — which is inherent to offering REST. Where a tool returns `"true"`/`"false"`
strings or comma-joined params, the router adapts to/from real JSON types (bool, arrays).

### 3.2 Carried over unchanged in v1 (must not regress)

This change is **additive**. Everything below keeps working exactly as it does today; the
composition in §3.1 must preserve each one, and the test suite (§10) must prove it. If any
of these changes, that's a bug, not part of this work.

| # | Carried over | Guarantee | At risk because |
|---|---|---|---|
| 1 | **`/mcp`** (FastMCP streamable app + all registered tools) | Same path, same JSON-RPC behaviour, same `GATEWAY_SERVER__AUTH_TOKENS` bearer auth | It moves from top-level app to mounted sub-app (see §3.1 — lifespan + path prefix) |
| 2 | **`gw` CLI** | Unchanged **in v1** — still a pure MCP client of `/mcp`; no CLI code touched. (Migrates to REST wholesale later, §9 — not permanent.) | Depends entirely on #1 |
| 3 | **`/v1/reminders`** — `GET /v1/reminders`, `POST /v1/reminders/sync`, `PUT/DELETE /v1/reminders/{id}` | Byte-for-byte wire protocol: snapshot/`since` sync, LWW-on-`updated_at`, tombstones, `409` stale, error envelope | Same app whose top-level structure changes; carried as plain Starlette routes, **not** ported to FastAPI |
| 4 | **`/v1/geocode`** — `GET /v1/geocode` | Same query params (`q`, or `lat`+`lon`) and responses | As #3 |
| 5 | **Reminders auth** — `GATEWAY_REMINDERS__API_TOKENS`, in-handler check | Unchanged; **not** replaced by the new scoped tokens in v1 | New scoped auth is introduced alongside it (§4.4); must not accidentally start gating these routes |
| 6 | **Tool modules** (`karakeep.py`, `email.py`, all others) | Function signatures and return shapes unchanged — the API *calls* them, never edits them | MCP + CLI depend on them; the reuse layer must adapt at the router, not by changing tools |
| 7 | **Reminders store** (`gateway/reminders/store.py`) | Untouched | — |
| 8 | **Existing config** — `GATEWAY_SERVER__*`, `GATEWAY_REMINDERS__*`, all tool config | Unchanged; the new `GATEWAY_API__CLIENTS` is purely additive | — |
| 9 | **`--transport stdio`** path | Unaffected — only `_run_http` is restructured | — |
| 10 | **Middleware behaviours** — `_DisconnectMiddleware` (swallow `ClientDisconnect`) and the `/mcp` `BearerAuthMiddleware` | Equivalent behaviour preserved in the FastAPI composition | They currently wrap the MCP Starlette app; the rewrite must re-attach them |
| 11 | **Deployment** — container, Traefik host router, port 4000 | No infra routing change; only the new `GATEWAY_API__CLIENTS` secret is added (§8) | — |

Items **1, 3, 4, 10** are the ones the composition actively puts at risk; the rest are
"don't touch." The regression tests in §10 cover 1/2/3/4 explicitly.

---

## 4. Auth & scopes

### 4.1 Client/token model

Config gains an `ApiConfig` (in `gateway/config.py`), populated from a single JSON env
var (same approach as `GATEWAY_GCAL__TOKEN_JSON`):

```
GATEWAY_API__CLIENTS=[
  {"name": "iphone", "token": "<random>", "scopes": ["bookmarks:*", "email:read"]},
  {"name": "readonly-laptop", "token": "<random>", "scopes": ["*:read"]}
]
```

```python
class ApiClient(BaseModel):
    name: str
    token: str
    scopes: list[str]

class ApiConfig(BaseModel):
    clients: list[ApiClient] = []
```

(pydantic-settings JSON-decodes a complex list field from the env var automatically — no
custom decoder needed.)

### 4.2 Scope grammar

`<domain>:<verb>` where `verb ∈ {read, write}`.

- `read` → safe/`GET` operations. `write` → `POST`/`PUT`/`PATCH`/`DELETE`.
- Wildcards: `*` (everything), `<domain>:*` (all verbs in a domain), `*:read`
  (read anything).
- A route declares the scope it needs, e.g. `Depends(require("bookmarks:read"))`.
- Satisfaction: required `bookmarks:read` is granted if the client holds any of
  `bookmarks:read`, `bookmarks:*`, `*:read`, `*`.

### 4.3 Enforcement

A FastAPI dependency `require(scope)`:

1. Reads `Authorization: Bearer <token>`; constant-time (`hmac.compare_digest`) compares
   against each configured client token.
2. No/invalid token → **401** `unauthorized`.
3. Token valid but scope not satisfied → **403** `forbidden`.
4. On success returns the matched `ApiClient` (available to handlers for logging).

The bearer scheme is declared to OpenAPI so `/v1/docs` shows the auth requirement and
per-route scopes.

### 4.4 Relationship to existing auth (transitional)

Three token mechanisms coexist after this lands, converging later (§9):

| Surface | Auth today | After v1 |
|---|---|---|
| `/mcp` | `GATEWAY_SERVER__AUTH_TOKENS` (middleware) | unchanged |
| `/v1/reminders`, `/v1/geocode` | `GATEWAY_REMINDERS__API_TOKENS` (in-handler) | unchanged (frozen protocol) |
| `/v1/bookmarks`, `/v1/emails`, … | — | `GATEWAY_API__CLIENTS` scoped tokens |

---

## 5. Error & response conventions

- **Error envelope** matches the existing API: `{"error": {"code": "...", "message":
  "..."}}`. Exception handlers translate FastAPI validation errors (422), `HTTPException`,
  and uncaught backend errors into this shape (FastAPI's default `{"detail": ...}` is
  overridden for consistency).
- **Backend error mapping:** tool functions call external services with
  `httpx` and `raise_for_status()`. Routers catch `httpx.HTTPStatusError` and map upstream
  4xx/5xx to a sane status + `{"error": {"code": "upstream_error", ...}}`; missing
  resources map to `404 not_found`.
- **Timestamps** RFC 3339 UTC, consistent with the reminders protocol.
- **Success** returns the resource/collection directly as typed JSON (no `status`
  wrapper for reads; mutations may return the affected resource).

---

## 6. Resource design — v1

Base prefix `/v1`. Message-IDs and other ids that contain URL-unsafe characters are
URL-encoded in the path.

### 6.1 Bookmarks (domain `bookmarks`, backend Karakeep via `gateway/tools/karakeep.py`)

| Method & path | Backing tool | Scope |
|---|---|---|
| `GET /v1/bookmarks?q=&limit=&cursor=` | `search_bookmarks` | `bookmarks:read` |
| `POST /v1/bookmarks` | `create_bookmark` | `bookmarks:write` |
| `GET /v1/bookmarks/{id}` | `get_bookmark` | `bookmarks:read` |
| `GET /v1/bookmarks/{id}/content` | `get_bookmark_content` | `bookmarks:read` |
| `PATCH /v1/bookmarks/{id}` | `update_bookmark` | `bookmarks:write` |
| `PUT /v1/bookmarks/{id}/tags` | `attach_tags` | `bookmarks:write` |
| `DELETE /v1/bookmarks/{id}/tags` | `detach_tags` | `bookmarks:write` |
| `GET /v1/tags` | `list_tags` | `bookmarks:read` |
| `GET /v1/lists` | `get_lists` | `bookmarks:read` |
| `POST /v1/lists` | `create_list` | `bookmarks:write` |
| `PUT /v1/lists/{list_id}/bookmarks/{id}` | `add_to_list` | `bookmarks:write` |
| `DELETE /v1/lists/{list_id}/bookmarks/{id}` | `remove_from_list` | `bookmarks:write` |

Request bodies (pydantic; router adapts to the tool's params):

- `POST /v1/bookmarks`: `{ "type": "link"|"text", "content": str, "title"?: str }`.
- `PATCH /v1/bookmarks/{id}`: `{ "title"?: str, "note"?: str, "archived"?: bool,
  "favourited"?: bool }` — bools are converted to the tool's `"true"`/`"false"` strings.
- `PUT|DELETE /v1/bookmarks/{id}/tags`: `{ "tags": [str] }` — array joined to the tool's
  comma-separated string.
- `POST /v1/lists`: `{ "name": str, "icon": str, "parent_id"?: str }`.

**Known gap:** there is no `delete_bookmark` tool, so no `DELETE /v1/bookmarks/{id}` in
v1. Adding one means adding the tool first (out of scope here; note it).

### 6.2 Email (domain `email`, backend IMAP via `gateway/tools/email.py`)

Read-mostly. The email id is the **Message-ID** header value (URL-encoded in the path).

| Method & path | Backing tool | Scope |
|---|---|---|
| `GET /v1/folders` | `list_folders` | `email:read` |
| `GET /v1/emails?folder=&limit=` | `list_emails` | `email:read` |
| `GET /v1/emails?unread=true&limit=` | `fetch_unread_emails` | `email:read` |
| `GET /v1/emails?q=&search_in=&folder=&limit=` | `search_emails` | `email:read` |
| `GET /v1/emails/{message_id}/body` | `fetch_email_body` | `email:read` |
| `PATCH /v1/emails/{message_id}` | `mark_email_read` | `email:write` |

`GET /v1/emails` dispatches by query params: `q` present → search; else `unread=true` →
unread; else → list. `search_in ∈ {subject, from, body, all}` (default `all`), passed
through to the tool. `PATCH /v1/emails/{message_id}` body `{ "read": true }` maps to
`mark_email_read` (only `read: true` is meaningful given the tool; reject others).

---

## 7. Discoverability

- FastAPI serves `GET /v1/openapi.json` (full schema incl. the bearer security scheme and
  per-route scopes) and `GET /v1/docs` (Swagger UI). Set `openapi_url="/v1/openapi.json"`,
  `docs_url="/v1/docs"`; title "Gateway API", versioned; routers tagged by domain
  (`bookmarks`, `email`).
- The legacy `/v1/reminders`/`/v1/geocode` routes are mounted as plain Starlette routes
  and won't appear in OpenAPI until they're ported (§9) — documented, not a bug.

---

## 8. Deployment (infra)

- Add `GATEWAY_API__CLIENTS` to `composition-gateway`'s `environment_vars.j2`, sourced
  from a new vault var (e.g. `vault_gateway_api_clients`, a JSON array). Per-client tokens
  are generated with `openssl rand -hex 32` and vaulted.
- **No Traefik change**: the host router already forwards all of `gateway.{domain}` to
  `:4000`, so `/v1/*`, `/v1/docs`, and `/v1/openapi.json` are exposed automatically.
- **Security note:** because Traefik exposes this publicly (behind TLS), scoped tokens are
  the whole defense — the iOS app should get the narrowest scope set it needs, and
  `/v1/docs` is reachable to anyone who can reach the host (it exposes shape, not data;
  acceptable, but note it).

---

## 9. Follow-ups (not in v1)

- **Port reminders/geocode to FastAPI + converge auth:** rewrite the existing
  `/v1/reminders`+`/v1/geocode` handlers as FastAPI routers (they are plain Starlette
  routes today, mounted as-is and therefore **absent from `/v1/openapi.json` and
  `/v1/docs`** — porting them to routers is precisely what makes them appear in the
  generated OpenAPI). At the same time, move them onto the scoped-token model
  (`reminders:*`, `geocode:read`) and retire `GATEWAY_REMINDERS__API_TOKENS`. The
  wire protocol (paths, request/response bodies, sync semantics) must stay
  byte-for-byte identical — this is a framework/auth port, not a protocol change.
  Deferred out of v1 to avoid churning the frozen reminders protocol in the same change
  that introduces the framework. Backward-compat plan: honour legacy reminders tokens as
  an implicit `reminders:*` client during the transition.
- **More domains:** Calendar, Notes/Issues, Location — same router + reuse pattern. These
  are also the **precondition for the CLI migration** below: the CLI can't leave MCP until
  the API covers its whole command surface.
- **Migrate the `gw` CLI to REST (wholesale).** Once the API's domain coverage ⊇ the CLI's
  surface, switch the CLI from MCP to REST in one change:
  - **Coverage gate.** The CLI has command groups for calendar, reminders, contacts,
    email, notes, bookmarks, location, issues. All except contacts must have REST
    endpoints first (this pulls the "More domains" item, plus the reminders/geocode port,
    into hard prerequisites).
  - **Client rewrite.** Replace `gateway/cli/client.py`'s JSON-RPC `tools/call` +
    SSE-envelope parsing with plain REST calls (typed JSON, standard status codes). Per
    the target layering, the CLI stops touching `/mcp` entirely.
  - **Auth change.** The CLI authenticates with a scoped `GATEWAY_API__CLIENTS` token
    (likely broad — e.g. `*` — since it's the owner's shell), replacing the MCP
    `GATEWAY_TOKEN`/`GATEWAY_SERVER__AUTH_TOKENS` path. Update the `gateway-cli` skill and
    the CLI's `--token`/env docs.
  - **No mixed state.** The switch is atomic per the decision (§2.6): the CLI is 100% MCP
    before it and 100% REST after; it is never split across transports.
  - **Contacts caveat (open detail).** `gw contacts` has no REST target (macOS-only,
    excluded — §1). Against the deployed Linux container it is already non-functional
    (contacts tools aren't registered there), so the wholesale switch effectively retires
    `gw contacts` rather than leaving a lone MCP command. Decide at migration time: drop
    the command, or keep it as an explicitly MCP-only exception (which would violate
    "never mixed" — dropping is cleaner).
- **`delete_bookmark`** tool + `DELETE /v1/bookmarks/{id}`.
- Optional: rate limiting / request logging per client.

---

## 10. Testing

- **Auth unit tests** (`tests/api/test_auth.py`): token match/no-match (401), scope
  satisfaction incl. wildcards, insufficient scope (403), verb→scope mapping.
- **Router tests** (`tests/api/test_bookmarks.py`, `test_email.py`) via FastAPI
  `TestClient`, with the tool modules' network boundary mocked (monkeypatch
  `karakeep._client` / `email._connection`): assert routing, request-model validation,
  the bool/array↔tool-param adaptation, response shape, and backend-error → envelope
  mapping.
- **Carry-over regression tests** (guard §3.2), all against the **composed** app via
  `TestClient` with lifespan enabled:
  - `/mcp` still completes a real `tools/call` (the §3.1 lifespan + path-prefix gotcha).
  - `/v1/reminders` (a `GET` and a `PUT`) and `/v1/geocode` still respond with their
    existing shapes and are still gated by `GATEWAY_REMINDERS__API_TOKENS` — **not** by
    the new scoped tokens (carry-over items #3–#5).
  - The `/mcp` `BearerAuthMiddleware` and `_DisconnectMiddleware` behaviours survive the
    recomposition (item #10).
- **OpenAPI smoke test**: `GET /v1/openapi.json` is valid, includes the bearer scheme and
  the expected new paths/scopes — and (asserting the §9 boundary) does **not** list
  `/v1/reminders`/`/v1/geocode` in v1.
- Existing suites (`tests/test_reminders_http.py`, `tests/test_http_auth.py`, CLI tests)
  must stay green unchanged — this change is additive.

---

## 11. Contract summary (must not get wrong)

1. The API is **additive** — MCP, the CLI, and `/v1/reminders`/`/v1/geocode` are
   untouched in v1.
2. Routers **reuse existing tool functions**; no backend logic is re-implemented.
3. Auth is **per-client scoped bearer tokens** (`domain:verb` + wildcards); 401 for bad
   token, 403 for insufficient scope.
4. Error envelope is `{"error": {"code", "message"}}` everywhere, incl. validation and
   upstream errors.
5. FastAPI is mounted as the top app with MCP at `/mcp`; **the FastAPI lifespan must drive
   the MCP session manager** or `/mcp` breaks.
6. Contacts has no REST surface (macOS-only, not in the container).
