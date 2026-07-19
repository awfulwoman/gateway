# Convert `gateway/tools/calendar.py` from EventKit → Google Calendar (OAuth)

## Context

Gateway's calendar tool (`gateway/tools/calendar.py`) is the last piece still using
Apple **EventKit** (reminders already migrated to the native SQLite store). EventKit
only works inside a GUI/Aqua login session on malcolm, so it breaks when Gateway runs
headless over launchd/SSH. The calendars Charlie actually cares about live in **Google
Calendar** (including the shared "Myrtle" calendar), so the macOS bridge is both fragile
and pointing at the wrong source of truth.

Goal: reach those calendars directly via the Google Calendar API v3, which works fully
headless. Auth model chosen: **OAuth "Desktop app" flow** — Gateway acts *as Charlie*,
so created events keep her as organizer and every calendar her account can see is
visible with no per-calendar sharing.

The six MCP tool **function signatures stay byte-for-byte identical**, so the MCP
contract, the `gw calendar` CLI (`gateway/cli/commands/calendar.py`), and its tests
(`tests/cli/test_calendar.py`, which mock at the `call_tool` boundary) are all
unaffected. Only the backend implementation changes.

## Auth design (OAuth desktop)

- **Scope:** `https://www.googleapis.com/auth/calendar` (read/write).
- **Bootstrap (one-time, on a machine with a browser — Charlie's Mac):** a new
  `python -m gateway.gcal_auth` runs `InstalledAppFlow.from_client_secrets_file(...).run_local_server(port=0)`
  against a downloaded OAuth **Desktop** client `credentials.json`, and writes
  `token.json` (contains refresh_token, client_id, client_secret, token_uri — enough to
  refresh forever without `credentials.json` at runtime).
- **Runtime:** load `Credentials.from_authorized_user_file(token_path, SCOPES)`; if
  expired, auto-refresh and best-effort write the refreshed creds back to `token_path`.
  Build the API client with `googleapiclient.discovery.build("calendar", "v3",
  credentials=creds, cache_discovery=False)`, cached in a module global like the current
  `_ek_store`.

## Changes

### 1. Dependencies — `pyproject.toml`
- Add `google-api-python-client>=2`, `google-auth>=2`, `google-auth-oauthlib>=1`.
- Remove `pyobjc-framework-EventKit>=10` (calendar was its only consumer; reminders
  migrated off it, contacts uses `pyobjc-framework-Contacts` which stays).

### 2. Config — `gateway/config.py`
- Add `GCalConfig(BaseModel)` with `token_path: str = ""`.
- Add `gcal: GCalConfig = GCalConfig()` to `Config`. (Env: `GATEWAY_GCAL__TOKEN_PATH`.)

### 3. Rewrite `gateway/tools/calendar.py`
Keep the pure helpers, replace the EventKit ones. Preserve every tool signature and the
`_event_to_dict` output keys (`event_id, title, start, end, all_day, location, notes,
calendar, url`) so `fmt.calendar_events`/`fmt.calendars` and tests keep working.

- **Keep** `_parse_period(period)` unchanged (pure datetime; returns UTC-aware
  start/end). Its `.isoformat()` yields RFC3339 that the API accepts directly for
  `timeMin`/`timeMax`.
- `init(config: GCalConfig)` + module-global `_config` (mirror `karakeep.init`).
- `_get_service()` — build/cache the Calendar service from `token_path`, refreshing as
  above; assert configured with a clear message (pattern of `karakeep._client`).
- **Event-id encoding (key design point):** a Google `eventId` is unique only *within a
  calendar*, but update/delete need the `calendarId` too. Return
  `event_id = f"{calendar_id}::{event_id}"`; a helper `_split_id(s)` splits it back
  (falling back to `("primary", s)` when no `::`). This preserves the single-arg
  update/delete signatures.
- `_event_to_dict(ev, cal_id, cal_summary)` — map a Google event resource: `summary`→
  title, `start`/`end` from `dateTime` else `date`, `all_day = "date" in ev["start"]`,
  `description`→notes, `htmlLink`→url, `calendar = cal_summary` (passed in, since the
  event resource doesn't carry its calendar's name), encoded `event_id`.
- `list_calendars()` — `service.calendarList().list()`; return
  `{name: summary, id, color: backgroundColor}`.
- `list_calendar_events(period)` — `_parse_period`, then for each entry in
  `calendarList` call `events().list(calendarId, timeMin, timeMax, singleEvents=True,
  orderBy="startTime")`; aggregate, convert, sort by `start`.
- `search_calendar_events(query, days_ahead=90)` — forward window `now .. now+days`,
  per-calendar `events().list(..., q=query, singleEvents=True, orderBy="startTime")`.
  Note: Google `q` is full-text (summary/description/location/attendees) — broader and
  better than the old title/location/notes substring match.
- `create_calendar_event(...)` — resolve `calendar_name`→`calendarId` via `calendarList`
  (case-insensitive summary match, else `"primary"`); body `summary/location/description`
  + `start`/`end` as `{"dateTime": <naive→local-tz isoformat>}` (reuse the current
  naive→`.astimezone()` behavior from the old `_ns_date`); `events().insert(...)`. Return
  `{status: "created", title, start, end, event_id: "<cal>::<id>"}`.
- `update_calendar_event(...)` — `_split_id`, build a body of only non-empty fields,
  `events().patch(calendarId, eventId, body=...)`.
- `delete_calendar_event(...)` — `_split_id`, `events().delete(calendarId, eventId)`.
- Wrap API errors (`googleapiclient.errors.HttpError`) into the existing
  `{"status": "error", "message": ...}` shape (matches current "Event not found"/"Failed
  to …" returns).
- `register(mcp)` unchanged.

### 4. New `gateway/gcal_auth.py`
Standalone one-time bootstrap: `InstalledAppFlow` → `run_local_server` → write
`token.json`. Runnable as `python -m gateway.gcal_auth [credentials.json] [token.json]`.

### 5. Wire init — `gateway/main.py`
Change `calendar.register(mcp)` to `calendar.init(config.gcal)` then
`calendar.register(mcp)` (matches every other tool's init/register pair).

### 6. Infra role (separate repo `infra/roles/system-mcp-gateway/`)
- `defaults/main.yaml`: add `system_mcp_gateway_gcal_token_path` (a path under the repo
  data dir, e.g. `{{ system_mcp_gateway_repo_dir }}/data/gcal_token.json`) and reference
  a new vaulted secret `vault_gateway_gcal_token_json`.
- Add an Ansible task to write the vaulted token JSON to that path (mode `0600`), like
  other deployed secrets.
- `templates/env.j2`: add `GATEWAY_GCAL__TOKEN_PATH={{ system_mcp_gateway_gcal_token_path }}`.
- Vault the `token.json` produced by the bootstrap step.

### 7. Docs — `README.md`
Document the one-time bootstrap (create GCP project → enable Calendar API → OAuth
Desktop client → `python -m gateway.gcal_auth` → deploy `token.json`) and the new
`GATEWAY_GCAL__TOKEN_PATH` env var. Replace the EventKit/macOS-calendar mention.

## Tests
- `tests/cli/test_calendar.py` — unchanged (mocks `call_tool`; verify still green).
- New `tests/test_calendar.py` — unit-test the pure/mappable logic without network: mock
  `_get_service()` to return a fake service with canned `calendarList`/`events`
  responses; assert `_event_to_dict` mapping (timed vs all-day, url, calendar name),
  `event_id` encode/`_split_id` round-trip, that `create`/`update`/`delete` call
  `insert`/`patch`/`delete` with the right `calendarId`/`eventId`, and `_parse_period`
  edge cases.

## Verification
1. `uv sync` (pulls Google libs, drops EventKit).
2. Bootstrap locally: `python -m gateway.gcal_auth ~/credentials.json ./data/gcal_token.json`
   — browser consent, confirm `token.json` written.
3. Point local `.env` at it: `GATEWAY_GCAL__TOKEN_PATH=./data/gcal_token.json`.
4. `uv run pytest` — all green.
5. Run the server (`uv run gateway --transport http`) and exercise end-to-end via the
   CLI against the real account:
   - `gw calendar list-calendars` — shows Google calendars incl. Myrtle.
   - `gw calendar list-events today` / `... week`.
   - `gw calendar search <term>`.
   - `gw calendar create "Test" 2026-07-20T14:00:00 2026-07-20T15:00:00 --calendar Myrtle`
     → verify it appears in Google Calendar as created by Charlie; grab its `event_id`.
   - `gw calendar update <event_id> --title "Test 2"` then `gw calendar delete <event_id>`
     → verify in Google Calendar.
6. Deploy via the infra role (per `.claude/rules/deploy.md`) once vault secrets are in
   place; confirm it works headless on malcolm (the whole point — no GUI session needed).

## Follow-up (not code)
Update memory `gotcha_macos_tcc_eventkit_ssh` — the calendar TCC/GUI-session limitation
no longer applies once this lands.
