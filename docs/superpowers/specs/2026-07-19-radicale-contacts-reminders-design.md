# Radicale-backed Contacts and Reminders (behind the Gateway API) — design spec

**Date:** 2026-07-19
**Status:** Draft

## Motivation

Two of Gateway's tool groups have a storage ceiling:

- **Contacts** are macOS-only (`pyobjc-framework-Contacts`), **read-only**
  (lookup/search/list, no create/update/delete), and **absent from the Linux
  container** — so the REST-API spec had to explicitly exclude Contacts from its
  surface (`2026-07-19-rest-api-design.md` §6).
- **Reminders** live in a Gateway-native **SQLite** store. That's fine as a store,
  but it's a bespoke schema — no standard format, and nothing but Gateway can read
  it.

We want to back both with **Radicale** (a lightweight CalDAV/CardDAV server):
reminders become `VTODO`s, contacts become vCards. Contacts become **writable and
cross-platform** (they work in the container), both live in **standard,
interoperable formats**, and — as a bonus — native Apple clients *could* sync
Radicale directly in parallel, though that is **not** the primary access path.

### The architecture that makes this work: Radicale is *behind* Gateway

This is the load-bearing correction over the naive "point devices at CalDAV"
design. **Radicale is an internal storage engine behind the Gateway HTTP API. The
custom iOS app speaks plain JSON to Gateway; it never speaks CalDAV.** Gateway is
the *only* required DAV client of Radicale.

```
   custom iOS app ──JSON/HTTPS──▶  Gateway HTTP API  ──CalDAV/CardDAV──▶  Radicale
   (Apple Reminders/Contacts, optionally, ──native DAV──────────────────▶ ┘ )
```

**Why this is the whole point.** Radicale was dropped earlier because the
third-party **NowThis** iOS app couldn't communicate with it — it tried to speak
**CalDAV directly** to Radicale, and (per
[`plans/2026-07-17-location-reminders-owntracks.md`](../plans/2026-07-17-location-reminders-owntracks.md))
"no iOS task app does CalDAV-synced geofencing." Inserting Gateway as a
**JSON-translation layer** removes that failure mode entirely: the custom app gets
clean JSON-over-HTTPS with offline sync (the protocol the cancelled
`2026-07-18-reminders-ios-app-handoff.md` already specified), and Gateway absorbs
all CalDAV/CardDAV complexity server-side.

So this change is narrower than "adopt CalDAV": it **swaps the storage engine
behind the existing Gateway API** from SQLite to Radicale, while **preserving the
JSON wire contract** the app depends on.

### This reverses a same-day decision — deliberately, and differently

Earlier on 2026-07-19 reminders were migrated the *other* way — **out of** Radicale
**into** SQLite (`migrate_radicale_to_sqlite.py`, since deleted; commits `e859ca0`,
`442e6ae`), dropping the `caldav` dependency. That migration found Radicale **empty
(0 VTODOs)** and simplified onto a single local store, at a time when the only
Radicale client was NowThis-over-CalDAV, which had failed. The prior VTODO↔reminder
field mapping from the deleted script is recovered and reused below.

What's changed since: we're **not** asking any app to speak CalDAV anymore. Gateway
does, behind its JSON API. That removes the reason SQLite won last time.

## Goals

- **Radicale is the storage backend** for reminders (`VTODO`) and contacts
  (vCard). It sits **behind** the Gateway HTTP API.
- **The Gateway JSON API is preserved, not retired.** The custom iOS app's
  `/v1/reminders` offline-sync contract (snapshot/`since`, LWW-on-`updated_at`,
  tombstones, `409` stale) stays **byte-for-byte**; only what's underneath it
  changes.
- Contacts become **read/write, cross-platform, in-container**, and therefore gain
  a REST surface (removing the exclusion in the REST-API spec).
- Gateway speaks **CalDAV/CardDAV over HTTP** to Radicale — no coupling to
  Radicale's on-disk layout; any DAV server is swappable.
- MCP tool names, CLI verbs, and JSON shapes stay **stable** — only backends move.

## Non-goals

- **Devices are not required to sync Radicale directly.** Native Apple
  CalDAV/CardDAV sync is an optional parallel capability Radicale happens to
  enable; the supported client is the custom app via Gateway's JSON API.
- **Calendar stays on Google Calendar** — unchanged. Radicale hosts only contacts
  and reminders.
- No new autonomous behaviour (per `CLAUDE.md`); the one deterministic geofence →
  push trigger is unchanged in character.

## Correction vs the initial scoping answers

An earlier scoping question's "Radicale replaces it" option previewed *dropping*
`reminders/http.py` (`/v1`) and the iOS-app path. **That is superseded by the
clarified architecture:** the `/v1` JSON API and a custom iOS app are both
**retained** — the app is the reason to keep the API. "Radicale replaces" applies
to the **SQLite store (`reminders/store.py`) only**, not the HTTP API in front of
it. The other three answers stand unchanged: geofence triggering stays
Gateway-side, Contacts move to CardDAV, and Gateway talks DAV over HTTP.

## Configuration

New `RadicaleConfig` in `gateway/config.py`; add `radicale: RadicaleConfig` to
`Config`. (`RemindersConfig` once carried transitional
`base_url`/`username`/`password` for exactly this, removed in `442e6ae`;
reintroduced here under a dedicated `radicale:` prefix.)

```python
class RadicaleConfig(BaseModel):
    base_url: str = ""          # e.g. https://radicale.internal
    username: str = ""
    password: str = ""
    contacts_path: str = ""     # CardDAV addressbook collection
    default_list: str = "Reminders"   # VTODO collection when list unspecified
```

`.env.example`:

```
# Radicale (CalDAV/CardDAV) — internal storage backend for reminders + contacts
GATEWAY_RADICALE__BASE_URL=https://radicale.internal
GATEWAY_RADICALE__USERNAME=gateway
GATEWAY_RADICALE__PASSWORD=your-password
GATEWAY_RADICALE__CONTACTS_PATH=/gateway/contacts/
GATEWAY_RADICALE__DEFAULT_LIST=Reminders
```

`GATEWAY_REMINDERS__DB_PATH` is removed. `GATEWAY_REMINDERS__API_TOKENS` (the app's
auth on `/v1`) and `GATEWAY_REMINDERS__NOMINATIM_URL` are **kept** — the `/v1` API
and its auth survive; only the store behind it changes.

## Dependencies

- **Add** `caldav>=1.3` (pulls `icalendar`, `lxml`, `vobject`, `niquests` — the
  ~17-package tree dropped in `442e6ae`). Covers CalDAV (`principal.calendars()`,
  `cal.todos()`) and CardDAV (`principal.addressbooks()`); `vobject`/`icalendar`
  (de)serialise.
- **Remove** `pyobjc-framework-Contacts` (the `sys_platform == 'darwin'` dep) and
  the macOS-only contacts branch in `main.py` — contacts register unconditionally.

---

## Reminders: a Radicale-backed store behind the frozen `/v1` API

The design is a **backend swap**. `gateway/reminders/http.py` (the `/v1` routes)
and the sync protocol are **untouched**; `gateway/reminders/store.py` (SQLite) is
**replaced** by a CalDAV-backed store exposing the **same interface** the http
layer and MCP tools already call:

```
get(id) · list_reminders(since, include_deleted, list_name)
upsert(reminder) -> raises Stale(current)   # LWW guard preserved
soft_delete(id, updated_at) · now_utc() · now_after() · new_id()
gc_tombstones(older_than_days)
```

Everything above the store — `tools/reminders.py`, `reminders/http.py`,
`cli/commands/reminders.py` — keeps working unchanged.

### Field mapping (recovered from the deleted migration script)

| Reminder dict  | `VTODO` property |
|----------------|------------------|
| `id`           | `UID` |
| `title`        | `SUMMARY` (required, non-empty) |
| `notes`        | `DESCRIPTION` |
| `due`          | `DUE` (ISO date/UTC ts ↔ `DATE`/`DATE-TIME`) |
| `priority`     | `PRIORITY` (0/1/5/9 — already iCal-native) |
| `list`         | parent collection name |
| `done`         | `STATUS` `COMPLETED`/`NEEDS-ACTION` |
| `completed_at` | `COMPLETED` |
| `created_at`   | `CREATED`/`DTSTAMP` |
| `updated_at`   | **`X-GATEWAY-UPDATED-AT`** (see LWW below) |
| `deleted`      | **`STATUS:CANCELLED` + `X-GATEWAY-DELETED`** (tombstone, below) |
| `location`     | RFC 9074 `VALARM;PROXIMITY` (geofence, below) |

`_todo_to_dict` / `_build_vtodo` replace the SQLite `_row_to_dict`/`_dict_to_params`
pair; timestamps normalise to the existing `YYYY-MM-DDTHH:MM:SSZ` shape.

### Preserving the wire contract over CalDAV — the three impedance points

The `/v1` protocol is timestamp-LWW with tombstones and a `since` cursor; CalDAV is
ETag/sync-token with hard deletes. The store bridges them so the app sees no
change:

1. **`updated_at` / LWW.** The app supplies `updated_at`; `upsert` compares it and
   raises `Stale(current)` on `incoming <= existing`. Store it as
   **`X-GATEWAY-UPDATED-AT`** (app-authoritative, independent of Radicale's clock),
   *not* `LAST-MODIFIED` (server-set). Read it back for the LWW comparison and the
   `since` filter.
2. **Tombstones.** `/v1` returns deleted reminders (`deleted:true`) so the app can
   propagate deletions on incremental sync. **`soft_delete` does not DELETE the
   VTODO** — it sets `STATUS:CANCELLED` + `X-GATEWAY-DELETED:true` and bumps
   `X-GATEWAY-UPDATED-AT`, leaving a tombstone object in the collection.
   `list_reminders(include_deleted=False)` filters these out; a `since` sync
   includes them. `gc_tombstones` performs the *actual* CalDAV `DELETE` on
   tombstones older than N days. (Any native DAV client just sees a standard
   `CANCELLED` todo — normally hidden.)
3. **`since` cursor.** `list_reminders(since=ts)` fetches VTODOs from the
   VTODO-capable collections and filters `X-GATEWAY-UPDATED-AT > since` in Python
   (personal scale, as contacts already do). A CalDAV `sync-token`/time-range
   optimisation is a later option, not needed for v1.

Under the hood the store uses CalDAV **ETags** with `If-Match` for object-level
concurrency (retry once on `412`); this is invisible to the wire protocol.

### Lists ↔ collections

Each reminder `list` is a CalDAV calendar collection advertising `VTODO`.
`list_reminder_lists` enumerates VTODO-capable collections. Writing to an unknown
list **auto-creates** it (`principal.make_calendar(name=…,
supported_calendar_component_set=["VTODO"])`), preserving today's free-text-list
behaviour; unspecified → `radicale.default_list`.

### Geofence / location reminders (kept Gateway-side; data in the VTODO)

Reconciling "Radicale replaces SQLite" with "keep geofence in Gateway": geofence
**geometry rides inside the VTODO** as a portable RFC 9074 `VALARM;PROXIMITY` (no
SQLite sidecar — there is no SQLite anymore), while the **triggering machinery
stays Gateway/infra-native** (OwnTracks waypoints over MQTT + the Home-Assistant
notification subscriber). This is exactly the architecture in
[`plans/2026-07-17-location-reminders-owntracks.md`](../plans/2026-07-17-location-reminders-owntracks.md),
which this spec unblocks:

```
BEGIN:VALARM
ACTION:DISPLAY
PROXIMITY:ARRIVE            ; arrive→ARRIVE, leave→DEPART
DESCRIPTION:<title>
BEGIN:VLOCATION
URL:geo:<lat>,<lon>;u=<radius_m>
END:VLOCATION
END:VALARM
```

plus `X-GATEWAY-WAYPOINT-TST`/`-GEO` on the VTODO for waypoint disarming. The
`location` dict (`name`/`lat`/`lon`/`radius_m`/`trigger`) round-trips through
`_todo_to_dict`. Forward-geocoding still runs in `create_reminder` via Nominatim.

### Geocode module

`gateway/reminders/geocode.py` stays put (the `reminders/` package survives — only
`store.py`'s internals change). It keeps reading `nominatim_url` from
`RemindersConfig`.

### Removed / kept

- **Removed:** the SQLite implementation of `gateway/reminders/store.py` (the file
  is rewritten as a CalDAV-backed store with the same public interface); the SQLite
  schema, WAL pragmas, and `db_path` config.
- **Kept unchanged:** `gateway/reminders/http.py` (`/v1` routes, sync, tombstones,
  `409`), its `GATEWAY_REMINDERS__API_TOKENS` auth, `tools/reminders.py`,
  `cli/commands/reminders.py`, and the `Stale`/tombstone/`now_after` *concepts*
  (they map onto CalDAV as above).

---

## Contacts: CardDAV-backed, writable, cross-platform

### vCard 4.0 ↔ contact dict

The returned dict shape (`name`, `nickname`, `organisation`, `job_title`, `emails`,
`phones`, `addresses`, `birthday`, `urls`) is **preserved**, plus `id` (`UID`) so
contacts are addressable for update/delete.

| Contact dict   | vCard property |
|----------------|----------------|
| `name`         | `FN` (+ structured `N` on write) |
| `nickname`     | `NICKNAME` |
| `organisation` | `ORG` |
| `job_title`    | `TITLE` |
| `emails`       | `EMAIL` (repeatable) |
| `phones`       | `TEL` (repeatable) |
| `addresses`    | `ADR` (street/city/state/postal/country) |
| `birthday`     | `BDAY` |
| `urls`         | `URL` (repeatable) |
| `id`           | `UID` |

`vobject` parses/serialises the vCard body.

### Tools

Read tools keep names/signatures; the migration's payoff is **new write tools**:

| Tool | Status |
|------|--------|
| `lookup_contact(name)` / `search_contacts(query)` / `list_contacts(limit)` | unchanged |
| `create_contact(...)` / `update_contact(id, ...)` / `delete_contact(id)` | **new** |

The `CNContactStore` implementation and its TCC-permission dance in the install
script are removed. Contacts register unconditionally (no `sys.platform` gate).

### Unblocks Contacts in the REST API

The REST-API spec excluded Contacts because it was macOS-only and absent from the
container (§1, §6, §9 "Contacts caveat"). With CardDAV that no longer holds:
**Contacts can now get a `/v1/contacts` REST surface** (read + write), which is
what the custom iOS app uses to manage contacts. Adding that router follows the
REST-API spec's reuse pattern (router → existing `contacts.*` tool fns) and should
be folded into that effort; this spec's job is to make it *possible* by moving the
backend off macOS.

---

## Interaction with the REST-API spec (`2026-07-19-rest-api-design.md`)

- That spec **freezes the `/v1/reminders` wire protocol** and lists
  `gateway/reminders/store.py` as "untouched" (§3.2 #7). This spec **honours the
  frozen wire protocol** but **does** rewrite the store's internals (SQLite →
  CalDAV). These are compatible *provided the wire contract is preserved* — which
  the impedance-bridging above guarantees. The two efforts must land in a known
  order: **do the store swap and the REST work as separate changes**, each with the
  `/v1` regression tests green, so neither silently changes the app's contract.
- This spec **removes the Contacts exclusion** the REST spec was forced into.

## Migration

1. **Reminders (SQLite → Radicale).** One-shot
   `scripts/migrate_sqlite_to_radicale.py` — inverse of the deleted
   `migrate_radicale_to_sqlite.py`, reusing its field map. Reads the current
   `reminders.db`, writes one `VTODO` per row (`UID = id`, so re-runs are
   idempotent), recreating lists as collections, re-encoding locations as
   `VALARM;PROXIMITY`, and preserving `updated_at`/`deleted` as the `X-` props
   above. `--dry-run` supported; delete after use.
2. **Contacts (macOS → CardDAV).** One-shot import of a macOS/iCloud vCard export
   into the Radicale addressbook (`scripts/import_contacts_to_radicale.py` reading a
   `.vcf`); the manual export step is documented in the README.

Both scripts get pytest coverage mirroring the retired migration test.

## Infra / deployment

- **Radicale role** in `infra/` (Ansible): install, auth (htpasswd) for the single
  `gateway` DAV user, persistent collections dir, backups. Radicale can bind
  **localhost/internal only** — it is not internet-facing; Gateway reaches it
  in-process-network. (If native Apple direct-sync is later wanted, expose it via
  the existing reverse proxy then — out of scope now.)
- **Docker:** Contacts previously excluded from the container (pyobjc). With
  CardDAV, **Contacts now work in-container** — drop that README caveat. Reminders
  no longer need a mounted SQLite volume; Radicale is the store. Gateway's container
  gains `GATEWAY_RADICALE__*`.

## Testing

- Unit: `_todo_to_dict`/`_build_vtodo` and vCard↔dict round-trips from raw
  `.ics`/`.vcf` fixtures; LWW/tombstone/`since` semantics of the new store against a
  filesystem-backed ephemeral Radicale in a tmp dir.
- **Regression (critical):** the existing `tests/test_reminders_http.py` must stay
  **green unchanged** against the new store — proving the `/v1` wire contract
  (snapshot/`since`, LWW, `409`, tombstones) is byte-for-byte preserved.
- Contacts: CRUD via CardDAV incl. the 412-retry path; new CLI write verbs.

## What does NOT change

- The **`/v1/reminders` wire protocol** and its auth — the app's lifeline.
- MCP tool **names/signatures** and returned **JSON shapes** for reminders and
  existing contacts reads.
- **Google Calendar** integration.
- The **OwnTracks/MQTT/HA** geofence-notification pipeline (now reads geofence data
  from the VTODO instead of SQLite).
- Priority scale (0/1/5/9) — already iCal-native.

## Open questions / risks

- **Tombstone semantics for native clients.** If Apple clients ever sync Radicale
  directly, they'll see `CANCELLED` tombstones until GC. Acceptable (standard,
  usually hidden), but confirm before enabling direct sync.
- **Preserving unknown VTODO/vCard properties on write.** Round-tripping through
  Gateway's model must not clobber fields it doesn't model (subtasks `RELATED-TO`,
  recurrence, extra vCard fields). Recommend: read-merge-write preserving unknowns.
- **`caldav` CardDAV maturity** is thinner than its CalDAV support; if write
  ergonomics disappoint, fall back to raw `PROPFIND`/`PUT` via `DAVClient` with
  `vobject` bodies.
- **Two `since`/sync models under one API** if/when the REST-API spec's scoped
  auth converges the reminders routes — keep the timestamp-LWW contract until that
  convergence, don't leak CalDAV sync-tokens to the app.
- **New secret:** Radicale DAV credentials to manage/rotate.
```
