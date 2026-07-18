# Reminders JSON interchange — implementation plan

Design spec: `docs/superpowers/specs/2026-07-18-reminders-json-interchange-design.md`.
Read it first — this plan assumes its data model, sync rule (LWW on `updated_at`),
and `/v1` endpoint shapes.

## Context

Retire the Radicale/CalDAV backend for reminders. Gateway becomes the store
(SQLite), exposes a flat-JSON HTTP API at `/v1` (bearer-token auth) for a
to-be-built iOS app, and reconciles place names ↔ coords via the local Nominatim.
The MCP tools and `gw` CLI keep their surface but read/write the SQLite store. This
also retires the OwnTracks + HA geofencing plan
(`docs/superpowers/plans/2026-07-17-location-reminders-owntracks.md`) — geofencing
is on-device in the app.

No new runtime deps: `sqlite3` (stdlib), `starlette`/`uvicorn`/`httpx` already present.

---

## Part 1 — Store (`gateway/reminders/store.py`)

New package `gateway/reminders/` (`__init__.py`, `store.py`, `geocode.py`, `http.py`).

`store.py` — module-level `_config` + a per-process `sqlite3.Connection` (like
`tools/reminders.py`'s `init()` pattern):

- `init(config: RemindersConfig) -> None` — stash config; open connection lazily.
- `_conn()` — open `config.db_path` (create parent dir), `PRAGMA journal_mode=WAL`,
  `PRAGMA busy_timeout=5000`, `row_factory = sqlite3.Row`, run `CREATE TABLE IF NOT
  EXISTS` + index (schema verbatim from spec). Idempotent.
- `_row_to_dict(row) -> dict` / `_dict_to_params(d) -> dict` — map the flat
  `loc_*` columns ⇆ nested `location` object; `done`/`deleted` int⇄bool;
  `location` is `None` when `loc_lat` is NULL. Also handle the `extra` column:
  `_dict_to_params` JSON-encodes every key with no column of its own into `extra`
  (`None`/`{}` when there are none); `_row_to_dict` decodes `extra` and merges it
  back at top level, with first-class columns winning on collision. This is what
  keeps reserved (`parent_id`, `rrule`) and future fields from being dropped.
- `list_reminders(since=None, include_deleted=True, list_name=None) -> list[dict]`
  — `WHERE updated_at > ?` when `since`; `AND deleted=0` unless `include_deleted`;
  `AND list=?` when `list_name`. (Sync path wants tombstones; MCP/CLI path doesn't.)
- `get(id) -> dict | None`.
- `class Stale(Exception)` — carries the current stored dict.
- `upsert(reminder: dict) -> dict` — LWW: read existing; if none or
  `incoming.updated_at > existing.updated_at`, `INSERT … ON CONFLICT(id) DO UPDATE`
  storing verbatim, return stored; else `raise Stale(existing)`. Validates
  `title` non-empty and, when `location` present, that `lat`/`lon` exist.
- `soft_delete(id, updated_at=None) -> dict` — upsert a tombstone (`deleted=1`,
  `updated_at`=arg or `now_utc()`), same LWW guard.
- `gc_tombstones(older_than_days=30) -> int` — `DELETE WHERE deleted=1 AND updated_at < ?`.
- Helpers: `now_utc()` → RFC3339 `Z`; `new_id()` → `str(uuid4())`.

## Part 2 — Geocode (`gateway/reminders/geocode.py`)

Thin sync `httpx` client over local Nominatim (`config.nominatim_url`). Mirror
`tools/owntracks.py` httpx style.

- `forward(q: str) -> dict | None` — GET `{base}/search?q=&format=jsonv2&limit=1`
  → `{"name": display_name, "lat": float, "lon": float}` or `None`.
- `reverse(lat, lon) -> dict | None` — GET `{base}/reverse?lat=&lon=&format=jsonv2`.
- Send a `User-Agent` header (Nominatim requires one). 10s timeout; on network
  error return `None` (caller decides 400 vs skip).

## Part 3 — Config (`gateway/config.py`, `.env.example`) — done

Extend `RemindersConfig` (kept the old `base_url`/`username`/`password` CalDAV
fields alongside the new ones — `tools/reminders.py` and its tests still read them
until Part 6/8 retire CalDAV; don't remove them yet):

```python
from typing import Annotated
from pydantic import field_validator
from pydantic_settings import NoDecode

class RemindersConfig(BaseModel):
    base_url: str = ""       # transitional CalDAV fields, retired after cutover
    username: str = ""
    password: str = ""

    db_path: str = ""
    api_tokens: Annotated[list[str], NoDecode] = []
    nominatim_url: str = ""

    @field_validator("api_tokens", mode="before")
    @classmethod
    def _split(cls, v):
        return [t.strip() for t in v.split(",") if t.strip()] if isinstance(v, str) else v
```

**Gotcha:** a bare `mode="before"` validator is **not enough**. For fields typed
`list[str]`, pydantic-settings' `EnvSettingsSource` tries to `json.loads()` the raw
env string *before* any validator runs (even nested inside a plain `BaseModel`,
reached via `env_nested_delimiter`) — a comma string like `a,b` raises
`SettingsError`/`JSONDecodeError` at `Config()` construction, before your validator
ever sees it. The fix is `Annotated[list[str], NoDecode]` (pydantic-settings
≥2.x): it tells the env source to skip its own decode and hand the raw string
straight to the validator. Verified against pydantic-settings 2.14.0 — see
`tests/test_config.py`.

`.env.example`: drop `BASE_URL/USERNAME/PASSWORD`; add `DB_PATH`, `API_TOKENS`,
`NOMINATIM_URL` (values from the spec).

## Part 4 — HTTP API (`gateway/reminders/http.py`)

Starlette `Route`s + a `JSONResponse` helper. Import `store` and `geocode`.

- `_authorized(request) -> bool` — read `Authorization: Bearer <t>`; `hmac.compare_digest`
  against each `config.api_tokens`; empty token list ⇒ deny.
- `_err(status, code, message)` → `JSONResponse({"error": {...}}, status)`.
- Handlers (each does the auth check first, returns 401 otherwise):
  - `GET /v1/reminders` — parse `?since`; `{"server_time": now, "reminders": store.list_reminders(since, include_deleted=True)}`.
  - `PUT /v1/reminders/{id}` — body reminder; force `id` from path; if `location`
    has `name` but no `lat` → `geocode.forward`, 400 if unresolved; `store.upsert`
    → 200; `Stale` → 409 + `{"current": e.current}`; validation → 400.
  - `DELETE /v1/reminders/{id}` — optional `{updated_at}` body; `store.soft_delete` → 200.
  - `POST /v1/reminders/sync` — body `{since, changes[]}`; for each change run the
    same upsert+geocode logic, collecting `rejected` `[{id, current}]`; then
    `{"server_time": now, "reminders": store.list_reminders(since, include_deleted=True), "rejected": rejected}`.
    Compute `server_time` **before** applying changes so nothing is missed.
  - `GET /v1/geocode` — `?q=` → `forward`; `?lat=&lon=` → `reverse`; 404 if no match.
- Export `routes: list[Route]`.

## Part 5 — Wire into server (`gateway/main.py`)

```python
from gateway.reminders import store as reminders_store, http as reminders_http

# in create_server, before returning:
reminders_store.init(config.reminders)

# in _run_http (or create_server), attach routes to the MCP Starlette app:
app = mcp.streamable_http_app()
app.router.routes.extend(reminders_http.routes)   # /v1/* alongside /mcp
app = _DisconnectMiddleware(app)
```

`reminders_http` reads `config.reminders` via a module `init(config)` too (store
config for the auth token list + nominatim url), called in `create_server`.
Keep `stdio` transport working (routes only matter for http).

## Part 6 — MCP tools (`gateway/tools/reminders.py`, rewrite)

Same registered names/signatures; bodies call `store`:

- `list_reminder_lists()` — `SELECT DISTINCT list` over non-deleted rows.
- `list_reminders(include_completed=False, list_name="")` — `store.list_reminders(include_deleted=False, list_name=...)`, filter `done` unless `include_completed`.
- `create_reminder(title, due_iso="", notes="", list_name="", priority=0, location_name="", arrive_or_leave="arrive", radius_m=150)` —
  build dict with `new_id()`, `created_at=updated_at=now`; if `location_name`,
  `geocode.forward` → `location` (error dict if unresolved); `store.upsert`.
- `complete_reminder(title)` — substring match over non-done rows; set
  `done=True`, `completed_at=now`, bump `updated_at`; upsert.
- `delete_reminder(title)` — match; `store.soft_delete`.
- `search_reminders(query)` — substring over title/notes (incl. done, excl. tombstones).

`init(config)` still called from `main.py` — but geocode/store need config too;
have `tools/reminders.py` import the shared `store`/`geocode` and rely on their
`init`. (One `reminders.init` can init all three to keep `main.py` tidy.)

## Part 7 — CLI (`gateway/cli/commands/reminders.py`, `fmt.py`)

- `create`: add `--radius` (int, default 150), pass through to `create_reminder`.
- `fmt.reminders`: render `location` (`📍 name (arrive, 150m)`) and `due`/`done`.
- No new command groups needed (geocode is server-internal; expose `gw location
  geocode` later only if wanted — out of scope here).

## Part 8 — Migration (`scripts/migrate_radicale_to_sqlite.py`)

One-shot, run on malcolm (reads gateway `.env` for both old Radicale creds and new
`DB_PATH`/`NOMINATIM_URL`, like `migrate_reminders_to_radicale.py` does today):

- Connect to Radicale via `caldav`; iterate all VTODOs (incl. completed).
- Map SUMMARY→title, DESCRIPTION→notes, DUE→due, PRIORITY→priority, STATUS→done,
  COMPLETED→completed_at, calendar name→list, UID→id (preserve identity).
- Parse the old `[location: <arrive|leave> <name>]` marker out of notes →
  `geocode.forward(name)` → `location` (log & skip geofence if unresolved).
- `store.upsert` each. Print a summary (count, #located, #failed geocodes).
- Idempotent (re-runnable; UID keeps identity, LWW no-ops on equal timestamps).

Delete `scripts/migrate_reminders_to_radicale.py`.

## Part 9 — Tests

- `tests/test_reminders_store.py` — temp-file db: LWW accept/reject (`Stale`),
  tombstone + resurrect ordering by timestamp, `since` filter, `location`
  round-trip, unknown-key round-trip (`parent_id`/`rrule`/arbitrary key preserved
  via `extra`), list/list_name filter, `gc_tombstones`.
- `tests/test_reminders_http.py` — Starlette `TestClient`: 401 no/bad token,
  PUT/GET/DELETE happy paths, 409 stale + `current`, `POST /sync` batch with
  mixed accept/reject, `since` continuity, `/v1/geocode` fwd+reverse, 400 on
  unresolvable name. Monkeypatch `geocode.forward/reverse`.
- Rewrite `tests/test_reminders.py` + `tests/cli/test_reminders.py` — drop the
  CalDAV fakes; point `store.init` at a temp db; monkeypatch `geocode`. Behaviour
  preserved (create/list/complete/delete/search + location).
- `tests/test_geocode.py` — httpx mocked (monkeypatch), fwd/reverse/None.

## Order of work

1. Part 3 config + Part 1 store + store tests.
2. Part 2 geocode + geocode tests.
3. Part 6 MCP tools onto store; rewrite their tests → green.
4. Part 4 HTTP + Part 5 wiring + HTTP tests.
5. Part 7 CLI.
6. Part 8 migration script.
7. Full `uv run pytest`; then deploy (`.claude/rules/deploy.md`) and migrate live
   data on malcolm; retire Radicale from infra separately.

## Verification

- `uv run pytest`.
- Local server up (`GATEWAY_REMINDERS__API_TOKENS=test`, temp db):
  - `curl -H 'Authorization: Bearer test' localhost:4000/v1/reminders` → `{server_time, reminders:[]}`.
  - `curl -XPUT …/v1/reminders/<uuid> -d '{"id":"…","title":"Milk","updated_at":"…Z","created_at":"…Z"}'` → 200; re-GET shows it.
  - Re-PUT same id with an **older** `updated_at` → 409 + `current`.
  - `curl …/v1/geocode?q=<local place>` → coords (against deployed Nominatim once configured).
  - No/`Bearer wrong` → 401.
- `gw reminders create "Buy compost" --location "<real place>" --radius 200` → row
  with a real `location`; `gw reminders list` shows the 📍 line.
- Migration dry-run against current Radicale data on malcolm; spot-check counts and
  one geocoded location.

## Non-goals (this plan)

- The iOS app itself — built in a **separate project** from its own self-contained
  brief: `docs/superpowers/specs/2026-07-18-reminders-ios-app-handoff.md`. This plan
  only delivers the `/v1` API + store it targets.
- Subtasks, recurrence, multi-user, real-time push, per-field merge.
- A public `gw geocode` command (server-internal for now).
- Removing `caldav`/`icalendar` from deps — keep until after migration, drop then.
