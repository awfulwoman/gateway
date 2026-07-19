# Calendar tool: EventKit → Google Calendar (OAuth)

**Date:** 2026-07-19
**Status:** Done
**Audience:** the developer implementing the change inside the Gateway repo. Assumes
familiarity with the existing tool pattern (`init`/`register`, one module per source).
Companion implementation plan: `docs/superpowers/plans/2026-07-19-calendar-google.md`.

---

## 1. Why

`gateway/tools/calendar.py` is the last module using Apple **EventKit**. EventKit only
works inside a GUI/Aqua login session, so it fails when Gateway runs headless under
launchd/SSH on malcolm. The calendars that matter (Charlie's personal + the shared
**Myrtle** calendar) actually live in **Google Calendar**. So the current bridge is both
fragile *and* pointed at the wrong source of truth.

This spec replaces the EventKit backend with the **Google Calendar API v3** over HTTPS —
fully headless — while keeping the tool's public contract identical.

### Goals

- Read/search/create/update/delete Google Calendar events from Gateway, headless.
- **Zero change** to the six MCP tool signatures, their JSON output shape, the `gw
  calendar` CLI, and the CLI tests.
- Deploy through the existing Ansible-vault pattern, like every other Gateway secret.

### Non-goals (v1)

- No recurrence editing (RRULE) authoring — recurring events are *read* (expanded via
  `singleEvents=True`) but not created/edited as series.
- No attendee/guest management, reminders/overrides, attachments, or free/busy queries.
- No all-day event *creation* (all-day events are read correctly; creation stays timed,
  matching today's behaviour).
- No service-account path. Auth is OAuth-as-the-user (decision on record: keeps Charlie
  as organizer, sees all her calendars without per-calendar sharing).

---

## 2. Auth model (OAuth "Desktop app")

Gateway authenticates **as Charlie**. Google identity, not a robot.

- **Scope:** `https://www.googleapis.com/auth/calendar` (read + write).
- **Client type:** OAuth 2.0 Client ID of type **Desktop app**, created in a Google
  Cloud project with the Calendar API enabled. Its download is `credentials.json`
  (client_id + client_secret).
- **Bootstrap (one-time, on a machine with a browser — Charlie's Mac):**
  `python -m gateway.gcal_auth <credentials.json> <token.json>` runs
  `InstalledAppFlow.from_client_secrets_file(credentials.json, SCOPES).run_local_server(port=0)`,
  opens the consent screen, and writes **`token.json`**. That file contains the
  `refresh_token`, `client_id`, `client_secret`, and `token_uri` — everything needed to
  refresh indefinitely at runtime **without** `credentials.json`.
- **Runtime (headless on malcolm):** load
  `Credentials.from_authorized_user_file(token_path, SCOPES)`. If the access token is
  expired, `google-auth` refreshes it using the refresh token; Gateway writes the
  refreshed credentials back to `token_path` best-effort (ignore write failures on a
  read-only mount — the refresh token itself is stable). Build the client:
  `googleapiclient.discovery.build("calendar", "v3", credentials=creds,
  cache_discovery=False)`, cached in a module global (replaces `_ek_store`).

**Failure modes to surface plainly** (return `{"status":"error","message":...}`, never
crash the server):

- `token_path` unset/missing → "Google Calendar not configured
  (GATEWAY_GCAL__TOKEN_PATH)".
- Refresh fails (revoked / expired refresh token) → "Google auth expired — re-run
  `python -m gateway.gcal_auth`".

**Refresh-token longevity caveat:** if the OAuth consent screen is left in *Testing*
mode, Google expires refresh tokens after 7 days. Publish the app (Testing → *In
production*; a single-user unverified app is fine for these scopes) so the token is
long-lived. Document this in the bootstrap steps.

---

## 3. Tool contract (unchanged surface)

Six MCP tools, **identical signatures and return-JSON keys** to today. The CLI
(`gateway/cli/commands/calendar.py`), the formatters (`gateway/cli/fmt.py`), and
`tests/cli/test_calendar.py` depend on these and must not need edits.

### 3.1 Event object (JSON returned to callers)

Same keys as the current `_event_to_dict`:

| Key | Source (Google event resource) | Notes |
|---|---|---|
| `event_id` | `f"{calendarId}::{event['id']}"` | **Composite** — see §3.2. |
| `title` | `summary` | `""` if absent. |
| `start` | `start.dateTime` else `start.date` | RFC3339 for timed, `YYYY-MM-DD` for all-day. |
| `end` | `end.dateTime` else `end.date` | as above. |
| `all_day` | `"date" in event["start"]` | bool. |
| `location` | `location` | `""` if absent. |
| `notes` | `description` | `""` if absent. |
| `calendar` | the calendar's `summary` | passed in during iteration (the event resource does not carry it). |
| `url` | `htmlLink` | `""` if absent. |

`fmt.calendar_events` slices `start[:16]`; both `2026-07-20T14:00:00+02:00` → `2026-07-20T14:00` and `2026-07-20` render correctly, so no formatter change is needed.

### 3.2 Composite event id (the one non-obvious design point)

A Google `eventId` is unique only **within a single calendar**, but `events.get/patch/
delete` all require a `calendarId`. The tool signatures for update/delete take a single
`event_id`. Resolve this by **encoding the calendar into the id**:

- On output: `event_id = f"{calendarId}::{eventId}"`.
- On input (`update`/`delete`): `_split_id(s)` → `(calendarId, eventId)`, splitting on the
  first `::`; if there's no `::`, fall back to `("primary", s)`.

This keeps the single-argument update/delete contract intact.

### 3.3 The six tools

| Tool | Google call(s) | Behaviour |
|---|---|---|
| `list_calendars()` | `calendarList().list()` | Return `[{name: summary, id, color: backgroundColor}]`. |
| `list_calendar_events(period)` | per calendar: `events().list(calendarId, timeMin, timeMax, singleEvents=True, orderBy="startTime")` | `period` parsed by the **unchanged** `_parse_period` (today/tomorrow/week/month/`YYYY-MM-DD:YYYY-MM-DD`). Aggregate across all calendars, convert, sort by `start`. |
| `search_calendar_events(query, days_ahead=90)` | per calendar: `events().list(..., q=query, timeMin=now, timeMax=now+days, singleEvents=True, orderBy="startTime")` | Google `q` is full-text (summary/description/location/attendees) — a superset of the old title/location/notes substring match. Forward-only window. |
| `create_calendar_event(title, start_iso, end_iso, location="", notes="", calendar_name="")` | `events().insert(calendarId, body)` | Resolve `calendar_name`→`calendarId` by case-insensitive `summary` match against `calendarList`, else `"primary"`. Body: `summary`, `location`, `description=notes`, `start`/`end` = `{"dateTime": <iso>}`. Naive input datetimes are localised via `.astimezone()` (same rule as the old `_ns_date`). Return `{status:"created", title, start, end, event_id}`. |
| `update_calendar_event(event_id, title="", start_iso="", end_iso="", location="", notes="")` | `events().patch(calendarId, eventId, body)` | `_split_id` first. Body carries **only non-empty** fields. Return `{status:"updated", event_id}`. |
| `delete_calendar_event(event_id)` | `events().delete(calendarId, eventId)` | `_split_id` first. Return `{status:"deleted", event_id}`. |

**Errors:** wrap `googleapiclient.errors.HttpError` into
`{"status":"error","message": <detail>}`. A 404 on update/delete maps to the existing
"Event not found" style message.

### 3.4 Reused as-is

`_parse_period(period)` is pure datetime logic and stays byte-for-byte. Its UTC-aware
`.isoformat()` output is valid RFC3339 for `timeMin`/`timeMax`.

---

## 4. Config & deployment

### 4.1 App config — `gateway/config.py`

```python
class GCalConfig(BaseModel):
    token_path: str = ""      # path to token.json (from the bootstrap flow)
```

Add `gcal: GCalConfig = GCalConfig()` to `Config`. Env var: `GATEWAY_GCAL__TOKEN_PATH`.

Wire it in `gateway/main.py`: `calendar.init(config.gcal)` before `calendar.register(mcp)`
(matches every other tool's init/register pair; calendar currently has no `init`).

### 4.2 Dependencies — `pyproject.toml`

- **Add:** `google-api-python-client>=2`, `google-auth>=2`, `google-auth-oauthlib>=1`.
- **Remove:** `pyobjc-framework-EventKit>=10` (calendar was its only consumer; reminders
  already migrated off it; contacts keeps `pyobjc-framework-Contacts`).

### 4.3 Infra role — `infra/roles/system-mcp-gateway/`

- `defaults/main.yaml`: add `system_mcp_gateway_gcal_token_path`
  (e.g. `{{ system_mcp_gateway_repo_dir }}/data/gcal_token.json`) and reference a new
  vaulted secret `vault_gateway_gcal_token_json` holding the bootstrap `token.json`
  contents.
- A task writes that vaulted JSON to the token path with mode `0600`.
- `templates/env.j2`: add
  `GATEWAY_GCAL__TOKEN_PATH={{ system_mcp_gateway_gcal_token_path }}`.

---

## 5. Bootstrap runbook (owner, one-time)

1. Google Cloud Console → new project → **enable Google Calendar API**.
2. OAuth consent screen → External → add yourself as a test user, then **Publish** the
   app (avoids the 7-day refresh-token expiry).
3. Credentials → Create OAuth client ID → **Desktop app** → download `credentials.json`.
4. On the Mac: `python -m gateway.gcal_auth ~/credentials.json ./data/gcal_token.json`,
   complete the browser consent.
5. Vault the resulting `token.json` as `vault_gateway_gcal_token_json`; deploy the role.

---

## 6. Testing

- `tests/cli/test_calendar.py` — **unchanged**; must stay green (mocks `call_tool`, so the
  backend swap is invisible to it).
- New `tests/test_calendar.py` — no network. Mock `_get_service()` to return a fake
  service whose `calendarList()`/`events()` return canned resources. Assert:
  - `_event_to_dict` mapping for timed vs all-day events (start/end, `all_day`, `url`,
    `calendar`).
  - `event_id` encode + `_split_id` round-trip, including the no-`::` → `primary`
    fallback.
  - `create`/`update`/`delete` call `insert`/`patch`/`delete` with the right
    `calendarId` and `eventId`, and that update sends only non-empty fields.
  - `_parse_period` cases (today/tomorrow/week/month/custom range/invalid).
  - `HttpError` → `{"status":"error", ...}`.

---

## 7. Acceptance / verification

Against the real Google account, with a bootstrapped `token.json`:

1. `uv sync` pulls the Google libs and drops EventKit; `uv run pytest` all green.
2. `gw calendar list-calendars` lists Google calendars including **Myrtle**.
3. `gw calendar list-events today` and `... week` return correct events, sorted.
4. `gw calendar search <term>` finds events by title/description/location.
5. `gw calendar create "Test" 2026-07-20T14:00:00 2026-07-20T15:00:00 --calendar Myrtle`
   → event appears in Google Calendar **created by Charlie** (organizer check); capture
   its `event_id`.
6. `gw calendar update <event_id> --title "Test 2"` then
   `gw calendar delete <event_id>` → both reflected in Google Calendar.
7. Deploy the infra role and confirm all of the above works **headless on malcolm** (no
   GUI login session) — the core reason for the migration.

---

## 8. Contract summary (must not get wrong)

1. **Six tool signatures and output keys unchanged** — CLI and its tests untouched.
2. `event_id` is **`calendarId::eventId`**; always split it before get/patch/delete.
3. Auth is **OAuth-as-user** via `token.json`; refresh silently, surface expiry as an
   actionable error, never crash.
4. Timed-event creation only; all-day events are read, not authored.
5. `_parse_period` is reused verbatim; its output feeds `timeMin`/`timeMax` directly.
6. Deploy `token.json` via Ansible vault, exactly like other Gateway secrets.

---

## 9. Follow-up (not code)

Update memory `gotcha_macos_tcc_eventkit_ssh`: once this lands, the calendar path no
longer depends on a macOS GUI/TCC session — the gotcha applies only to any remaining
EventKit-based features (none after this).
