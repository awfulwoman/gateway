# gateway-ios — build handoff

**Date:** 2026-07-20
**Status:** Active
**Repo:** `git@github.com:awfulwoman/gateway-ios.git` (empty — this is the greenfield brief)
**Supersedes:** [`2026-07-18-reminders-ios-app-handoff.md`](2026-07-18-reminders-ios-app-handoff.md)
(Cancelled — Reminders-only, written against the pre-Radicale backend; kept as history)

**Audience:** the agent/developer building the iOS app in the `gateway-ios` repo. This
document is **self-contained** — you do not need the Gateway server repository to build
against it. Every wire format the app depends on is reproduced here. Where a dependency
is **not yet built server-side**, it is flagged in bold — read §2 first.

---

## 1. What you are building

A personal iOS app — one user, the owner — that is the native client for a self-hosted
**Gateway** server. It talks **plain JSON over HTTPS** to Gateway; it never speaks
CalDAV/CardDAV, IMAP, or any backend protocol directly (Gateway is the translation
layer). Two domains:

- **Reminders** — offline-first, with on-device time + geofence notifications. *This is
  the reason the app exists*: no third-party iOS app does CalDAV-synced geofencing, so a
  custom client with on-device region monitoring, talking JSON to Gateway, is the only
  way to get it.
- **Contacts** — browse / search / create / edit / delete the owner's address book.

**The two domains are architecturally different — do not force them into one model:**

| | Reminders | Contacts |
|---|---|---|
| Server protocol | **Sync** (`/v1/reminders/sync`, LWW, tombstones, `since`) | **Plain REST CRUD** (`/v1/contacts`) |
| Local model | Offline-first; local store is source of truth; must work fully offline (geofences fire offline) | Online CRUD with a read-through cache for offline viewing; server is source of truth |
| Conflict handling | Last-write-wins on `updated_at` | None — last write to the server wins implicitly; no `updated_at`/tombstones on the wire |
| On-device system integration | Notifications + `CLCircularRegion` geofencing | None |

Reminders carries all the hard problems. Contacts is a thin CRUD screen. Build Reminders
first (it's unblocked); Contacts second (it is **blocked** — §2).

### v1 scope

- **Reminders:** browse grouped by list; create/edit/complete/delete (title, notes, due
  date/time, priority, list, optional geofence); time + location notifications;
  background + foreground sync.
- **Contacts:** browse alphabetically; search; view detail; create/edit/delete.
- **Settings:** server base URL + auth token.
- A read-only **reminders widget** (§9.1).

### Out of scope for v1

Reminder subtasks/nesting, recurrence; contact groups/photos/custom labels; sharing /
multi-user / multiple accounts; App Intents/Siri; real-time push. The reminders protocol
reserves room for subtasks/recurrence (§4) — round-trip those keys, don't act on them.

---

## 2. Prerequisites & current readiness — READ FIRST

The two halves are at different stages of server-side readiness.

### Reminders — **ready now**

`/v1/reminders`, `/v1/reminders/sync`, and `/v1/geocode` are live in production and
frozen. You can build and ship the entire Reminders half today against a running Gateway.
(The backend moved from SQLite to Radicale/CalDAV on 2026-07-19, but the wire contract is
**byte-for-byte identical** — the app cannot tell, and nothing in §4–§8 changed.)

### Contacts — **BLOCKED on Gateway-side work**

The Contacts endpoints in §5B (`/v1/contacts`) **do not exist yet**. Contacts currently
exists in Gateway only as MCP tools (for LLM agents) and a CardDAV backend — neither is a
JSON HTTP surface an app can use. The `/v1/contacts` REST router is **designed but
unbuilt**, in the Gateway repo at
`docs/superpowers/specs/2026-07-19-rest-api-design.md` §6.3.

**Before the Contacts half of this app can be built, someone must build `/v1/contacts` in
Gateway.** Two Gateway-side items are prerequisites:

1. **Build the `/v1/contacts` router** (REST-API spec §6.3) — the FastAPI resource layer
   that whole spec introduces does not exist yet either, so this is the larger of the two.
2. **Auth convergence (recommended, so the app uses one token).** `/v1/reminders` is
   authed by `GATEWAY_REMINDERS__API_TOKENS`; the new REST layer (`/v1/contacts`) uses
   scoped `GATEWAY_API__CLIENTS` tokens. To avoid the app juggling two tokens, converge
   reminders/geocode onto the scoped-token model at the same time (REST-API spec §9
   follow-up), so a single bearer token grants `reminders:*` + `contacts:*` + `geocode:read`.

Until those land, build Reminders and stub the Contacts UI behind a feature flag. §5B is
written against the §6.3 design so it's ready the moment the endpoints exist.

---

## 3. Connection & auth (shared)

- **Base URL**: a full URL the owner enters in Settings, e.g. `https://gateway.example.com`.
  The API lives under `/v1`. Do not hardcode; store it.
- **Auth**: every request carries `Authorization: Bearer <token>`. One fixed secret the
  owner pastes in Settings (per-device, independently revocable). Store base URL + token
  in the **Keychain**.
- **Transport**: HTTPS only (TLS at the server's reverse proxy).
- **401** = missing/invalid token → surface as "check your server URL and token."
- First-run onboarding: enter base URL + token, then a test `GET /v1/reminders` to confirm
  connectivity before proceeding.

Per §2, the eventual single token grants both reminders and contacts scopes. If Contacts
ships before auth convergence, Settings may need two token fields — treat that as a
fallback, not the goal.

---

# PART A — REMINDERS (ready to build)

## 4. The reminder object (wire format)

A reminder is a **flat JSON object**. All timestamps are **RFC 3339 UTC** with a `Z`
suffix (e.g. `2026-07-18T09:15:04Z`).

```json
{
  "id": "3f1c8b2e-....-uuid",
  "title": "Buy compost",
  "notes": "the peat-free kind",
  "due": "2026-07-20",
  "priority": 0,
  "list": "Reminders",
  "done": false,
  "completed_at": null,
  "location": {
    "name": "Späti, Boxhagener Str.",
    "lat": 52.5200,
    "lon": 13.4050,
    "radius_m": 150,
    "trigger": "arrive"
  },
  "created_at": "2026-07-18T09:15:04Z",
  "updated_at": "2026-07-18T09:15:04Z",
  "deleted": false
}
```

| Field | Type | Meaning / rules |
|---|---|---|
| `id` | string (UUID) | Stable identity. **The app generates it** (`UUID().uuidString`) when creating; never changes. |
| `title` | string | Required, non-empty. |
| `notes` | string \| null | Free text. |
| `due` | string \| null | **`YYYY-MM-DD`** = all-day → notify at **09:00 local** on that date (§7). **Full RFC 3339** (has `T`) = a specific time. Presence of `T` is the only signal; there is no separate all-day flag. |
| `priority` | int | `0` none · `1` high · `5` medium · `9` low. Map to a 4-tier UI. |
| `list` | string | List/group name. Lists are **implicit** — a list exists because a reminder names it. Default new reminders to `"Reminders"`. No separate list resource. |
| `done` | bool | Completion. |
| `completed_at` | string \| null | Set to "now" when `done`→true; null when →false. |
| `location` | object \| null | Geofence, or null. See below. |
| `created_at` | string | Set once at creation; never modified. |
| `updated_at` | string | **Critical for sync.** Set to the writer's current UTC time on *every* edit (incl. complete, delete). Drives LWW. |
| `deleted` | bool | Tombstone. Deletes are soft — send `deleted:true`, don't drop the row. |

**`location` object:** `lat`/`lon` authoritative and always present when set. `name` is an
optional display label. `radius_m` = geofence radius in metres (default 150). `trigger` =
`"arrive"` or `"leave"`.

**Forward-compat rule:** the server may add fields. **Preserve and round-trip any JSON
keys you don't recognise** — decode into your model, keep the originals, send them back on
`PUT`. `parent_id` and `rrule` are reserved for future subtasks/recurrence: in v1 treat
them **exactly as unknown keys** — don't model or act on them, keep them in `extraJSON`
(§6), round-trip unchanged.

## 5A. Reminders HTTP API

Base `{baseURL}/v1`, bodies `application/json`, bearer header on every request. Errors:
`{"error": {"code": "...", "message": "..."}}`.

| Method & path | Body | Returns |
|---|---|---|
| `GET /v1/reminders` | — | `{ "server_time": "…Z", "reminders": [ …objects… ] }` — **full set incl. tombstones** (`deleted:true`). |
| `GET /v1/reminders?since=<RFC3339>` | — | Same shape; only objects with `updated_at` **strictly greater than** `since` (still incl. tombstones). |
| `PUT /v1/reminders/{id}` | one full reminder object | `200` + stored object. `409` + `{ "current": <object> }` if **stale** (server has newer `updated_at`). `400` on validation error. |
| `DELETE /v1/reminders/{id}` | optional `{ "updated_at": "…Z" }` | `200` + tombstone. (≡ `PUT` with `deleted:true`.) |
| `POST /v1/reminders/sync` | `{ "since": "…Z" \| null, "changes": [ …objects… ] }` | `200` + `{ "server_time", "reminders", "rejected" }` — §5A.2. **Use this for normal sync.** |
| `GET /v1/geocode?q=<text>` | — | `{ "name", "lat", "lon" }` or `404`. |
| `GET /v1/geocode?lat=<n>&lon=<n>` | — | `{ "name", "lat", "lon" }` (reverse) or `404`. |

**Status codes:** `200` ok · `400` validation (empty title, or a `location.name` the
server couldn't geocode) · `401` bad/missing token · `404` unknown route / no geocode
match · `409` stale write (body carries the winning `current`).

### 5A.2 `POST /v1/reminders/sync`

Request:
```json
{ "since": "2026-07-18T09:00:00Z",
  "changes": [ { "id": "abc…", "title": "Milk", "done": true,
    "completed_at": "2026-07-18T09:19:00Z", "updated_at": "2026-07-18T09:19:00Z",
    "created_at": "2026-07-17T…Z" } ] }
```
Response:
```json
{ "server_time": "2026-07-18T09:20:11Z",
  "reminders": [ { "id": "def…", "title": "Call plumber", "updated_at": "2026-07-18T09:12:00Z" } ],
  "rejected": [ { "id": "ghi…", "current": { "…the server's newer object…": true } } ] }
```
- `reminders` = every object changed **server-side** since `since` (after applying your
  `changes`), incl. tombstones. Apply to local store.
- `rejected` = pushes the server declined (it held a newer `updated_at`). Replace your
  local copy with each `current` and clear its dirty flag — this device lost that race.

## 6. Reminders sync algorithm (implement exactly)

**Model:** whole-object **last-write-wins (LWW)** keyed on `updated_at`. No per-field
merge, no version vectors. Larger `updated_at` always wins — incl. deletes (a later
delete beats an earlier edit; a later edit resurrects an earlier tombstone). Single-user,
deliberately simple.

**Writer rule:** whenever the app changes a reminder (edit, complete, delete), set its
`updated_at` to `Date()` UTC **before** saving locally, and mark it **dirty**.

**A sync cycle:**
1. `POST /v1/reminders/sync` with `since` = the `server_time` persisted from the last
   successful sync (`null` on first sync → full set) and `changes` = all dirty reminders
   (full objects).
2. For each object in response `reminders`, apply LWW: replace the local copy **iff**
   incoming `updated_at` is newer (or local absent). Winning tombstones → stop
   showing/monitoring the reminder.
3. For each `rejected` entry, overwrite local with `current`, clear dirty.
4. Clear dirty on any pushed change **not** rejected.
5. Persist `server_time` as the new `since`.

**First sync / recovery:** `since = null` pulls everything and is always a safe reset —
do it on first launch and whenever the local store may be stale (e.g. after a restore).
The server GCs tombstones after ~30 days, so a very old `since` could miss a delete;
`since = null` avoids that.

**Clock caveat (accept, don't solve):** LWW uses device wall-clocks; single user + NTP
makes skew a non-issue. Do not build vector clocks.

**When to sync:** on foreground; on pull-to-refresh; after a local edit (debounce a few
seconds); from a background task (§8). No server push — the app always initiates.

### 6.1 Local data model (reminders)

SwiftData (or Core Data). The local model **is** the wire object plus local-only fields.
**Put the store in an App Group container** (`group.<bundle-id>`) so the widget (§9.1) can
read it — configure the `ModelContainer` with that shared URL from the start; retrofitting
is painful. The app is the only writer; the widget reads.

```
Reminder
  id: String            // UUID, == wire id, primary key
  title: String
  notes: String?
  due: Date?
  dueIsDateOnly: Bool    // derived from wire on decode; controls "09:00 local"
  priority: Int          // 0/1/5/9
  list: String
  done: Bool
  completedAt: Date?
  locName: String?; locLat: Double?; locLon: Double?; locRadiusM: Int?; locTrigger: String?
  createdAt: Date
  updatedAt: Date        // the LWW key
  deleted: Bool
  // local-only, never sent:
  dirty: Bool            // has unpushed local changes
  extraJSON: Data?       // verbatim unknown keys (incl. parent_id, rrule), re-merged on encode
```
Encode/decode helpers handle: `due` date-only vs timed (emit `YYYY-MM-DD` vs full RFC
3339); RFC 3339 UTC everywhere; `location` ⇄ flat `loc*` fields; merge `extraJSON` back on
encode.

## 7. Notifications & geofencing (reminders)

Request up front: **notifications** (`UNUserNotificationCenter`) and **location Always**
(region monitoring needs Always; explain why).

**Time reminders:** for each non-done reminder with a `due`, schedule a
`UNCalendarNotificationTrigger`. Date-only `due` → fire at **09:00 local** on the due date
(fixed v1 default). Reschedule on edit; cancel on complete/delete.

**Location reminders (on-device):**
- For each non-done reminder with a `location`, register a `CLCircularRegion` (`center` =
  lat/lon, `radius` = `radius_m`).
- `notifyOnEntry`/`notifyOnExit` from `trigger` (`arrive`→entry, `leave`→exit).
- On region event, fire a local `UNNotification` ("📍 <title>"). **Not** auto-completed —
  the owner completes manually.
- **iOS monitors at most 20 regions.** With >20 active location reminders, monitor the
  **20 nearest** to current location; re-evaluate on
  `startMonitoringSignificantLocationChanges`.
- Remove a region when its reminder is completed, deleted, or loses its location.

**Coordinates without Apple:** when the owner types a place name, resolve via
`GET /v1/geocode?q=<text>` and store the returned `lat`/`lon`/`name`. Do **not** use
`CLGeocoder`. A map-pin drop uses raw coordinates (optionally reverse-geocode via
`GET /v1/geocode?lat=&lon=` for a label).

## 8. Background sync (reminders)

Register a `BGAppRefreshTask` running one sync cycle periodically so notifications and
geofences reflect server-side changes from other devices / the CLI. Also sync on
launch/foreground and pull-to-refresh. Keep background work short: one
`POST /v1/reminders/sync`, apply results, reconcile notifications + monitored regions,
done.

---

# PART B — CONTACTS (blocked on `/v1/contacts` — §2)

Everything in Part B is written against the **designed-but-unbuilt** `/v1/contacts` router
(Gateway REST-API spec §6.3). Do not start it until those endpoints exist. It is
deliberately much simpler than Reminders: **plain REST CRUD, no sync protocol, no
tombstones, no `updated_at`.**

## 4B. The contact object (wire format)

```json
{
  "id": "a1b2c3d4-....-uuid",
  "name": "Alice Smith",
  "nickname": "Al",
  "organisation": "ACME Ltd",
  "job_title": "Engineer",
  "emails": ["alice@example.com", "alice@work.com"],
  "phones": ["+49 30 1234567"],
  "urls": ["https://alice.example.com"],
  "birthday": "1990-05-01",
  "addresses": [
    { "street": "1 Haupt Str.", "city": "Berlin", "state": "",
      "postal_code": "10115", "country": "Germany" }
  ]
}
```

| Field | Type | Rules |
|---|---|---|
| `id` | string | The contact's CardDAV `UID`. **Server-assigned on create** (unlike reminders — do *not* generate it client-side). Immutable. |
| `name` | string | Required, non-empty. Display name (`FN`). |
| `nickname` | string | May be `""`. |
| `organisation` | string | May be `""`. |
| `job_title` | string | May be `""`. |
| `emails` | [string] | May be empty. |
| `phones` | [string] | May be empty. |
| `urls` | [string] | May be empty. |
| `birthday` | string \| null | `YYYY-MM-DD` or null. |
| `addresses` | [object] | Each: `street`, `city`, `state`, `postal_code`, `country` (all strings, may be `""`). May be empty. |

No `created_at`/`updated_at`/`deleted` on the wire — Contacts is not a sync protocol.
Apply the same **forward-compat rule** as reminders: preserve and round-trip any unknown
keys.

## 5B. Contacts HTTP API (per REST-API spec §6.3)

| Method & path | Behaviour | Returns |
|---|---|---|
| `GET /v1/contacts?q=<text>` | Full-text search (name/nickname/email/phone/organisation) | `[ …contact… ]` |
| `GET /v1/contacts?name=<text>` | Name-only lookup | `[ …contact… ]` |
| `GET /v1/contacts?limit=<n>` *(no `q`/`name`)* | Alphabetical list, capped | `[ …contact… ]` |
| `POST /v1/contacts` | Create; body is a contact **without** `id` | `200/201` + created contact (with server `id`) |
| `PATCH /v1/contacts/{id}` | Update; body has any subset of fields | `200` + updated contact |
| `DELETE /v1/contacts/{id}` | Delete | `200` + `{ "status": "deleted", "id": … }` |

Dispatch on `GET /v1/contacts` mirrors emails: `q` → search; else `name` → lookup; else →
list.

**Auth:** scoped bearer token — `contacts:read` for `GET`, `contacts:write` for
`POST`/`PATCH`/`DELETE` (REST-API spec §4). Per §2, aim for one token covering both
domains.

### ⚠️ 5B.1 The `PATCH` "can't clear a field" gap (design around it)

The backing `update_contact` treats an **omitted or blank** field as *"leave unchanged,"*
not *"clear it"* — so a naïve PATCH cannot null out an email, birthday, etc. This is a
known limitation inherited from the tool layer (documented in REST-API spec §6.3).

Implications for the app until Gateway fixes it:
- **Edit that only adds/changes values** works fine via PATCH.
- **Removing** a value (deleting an email, clearing a birthday) is **not reliably
  expressible** through PATCH. Two options, pick one and note it in the UI:
  1. **Recommended interim:** implement "save edits" as **delete-then-recreate** when the
     edit removes any field — but note this **changes the `id`** (create assigns a new
     UID), which is acceptable for contacts (nothing references a contact by id long-term
     the way reminders' geofences do) but must be handled in the local cache.
  2. Disable field-removal in the editor and surface it as a known limitation until
     Gateway supports explicit-null PATCH.

Flag this to the Gateway maintainer as the first thing to fix once `/v1/contacts` exists.

## 6B. Local model & sync (contacts — the simple one)

No offline-first store, no LWW, no dirty/tombstone machinery. Contacts is **online CRUD
with a read cache**:

- **Read:** `GET /v1/contacts` on open / pull-to-refresh; cache the result (plain
  `Codable` structs persisted to the App Group container is enough) so the list renders
  offline. The **server is the source of truth**; the cache is a convenience.
- **Write:** `POST`/`PATCH`/`DELETE` go straight to the server and require connectivity.
  On success, update the cache from the response. On failure (offline), surface an error
  and do **not** silently queue — contacts have no conflict-resolution protocol, so
  offline write queuing would risk clobbering. (If offline contact editing is wanted
  later, it needs the same `updated_at`/LWW treatment reminders has — out of scope.)
- No background task needed for contacts.

Keep the contacts cache **separate** from the reminders SwiftData store — different
lifecycle, different guarantees. Don't entangle them.

---

# SHARED — UI, WIDGET, ACCEPTANCE

## 9. UI (v1, minimal, native)

**Reminders**
- **List**: grouped by `list`, incomplete first; title, due, priority indicator, 📍 for
  location reminders; swipe/tap to complete; swipe to delete.
- **Editor**: title, notes, due (date + all-day toggle → date-only vs timed), priority
  picker, list picker (free text / existing), optional location (search →
  `/v1/geocode`, or map pin) with radius + arrive/leave.

**Contacts**
- **List**: alphabetical by `name`; search field → `GET /v1/contacts?q=`.
- **Detail**: name, org, job title, emails/phones/urls (tap to call/mail/open),
  addresses, birthday.
- **Editor**: the contact fields; respect the §5B.1 removal caveat.

**Settings**: server base URL, token (Keychain), "test connection", manual "sync now"
(reminders).

## 9.1 Reminders widget (WidgetKit)

Read-only, **reminders only**. Extension in the same App Group (§6.1); its
`TimelineProvider` reads the shared reminders store directly — **no network calls**, it
reflects the last app sync.

- **Content**: next incomplete, non-deleted reminders, sorted by due (soonest first;
  undated last), then priority. Title + short due label ("Today"/"Tomorrow"/"Fri"/"—");
  📍 glyph for location reminders.
- **Families**: `systemSmall` (count due today + next one); `systemMedium` (next ~3–4);
  optional `accessoryRectangular` lock-screen (next + count).
- **Timeline**: one "now" entry + a refresh at the next due boundary (start of next day)
  so relative labels stay correct.
- **Refresh**: after every successful sync and after local edits, call
  `WidgetCenter.shared.reloadAllTimelines()`.
- **Tap**: opens the app. **Empty state**: "No reminders" / "All done".

## 10. Acceptance / verification

Point the app at a running Gateway (owner supplies base URL + token).

**Reminders**
1. Onboarding: wrong token → 401 surfaced; correct → `GET /v1/reminders` succeeds.
2. Create in app → appears server-side (owner checks via `gw` CLI) after sync.
3. Edit on server (CLI) → app reflects it after sync.
4. Conflict: edit same reminder on server + app while offline; on reconnect the newer
   `updated_at` wins and the loser adopts the winner (exercise the `rejected` path).
5. Complete/delete round-trip both directions; tombstones remove the item.
6. Time notification fires at due time (date-only → 09:00 local).
7. Location notification: geofence at a nearby place fires on crossing (Xcode location
   simulation ok).
8. Offline create/edit → pushes on reconnect.
9. Widget shows upcoming reminders; updates after a sync.

**Contacts** *(only once `/v1/contacts` exists — §2)*
10. List loads and renders offline from cache; search filters.
11. Create → appears server-side; server-assigned `id` stored.
12. Edit (add/change a field) round-trips.
13. Delete round-trips.
14. Offline write → clear error, no silent data loss.

### Protocol conformance unit tests (write these)

**Reminders:** LWW (newer replaces / older ignored / equal no-op); `rejected` handling
(local replaced by `current`, dirty cleared); winning tombstone removes item + cancels
its region/notification; `since` continuity (stored `since` == returned `server_time`);
wire round-trip (date-only vs timed `due`; location ⇄ flat fields; unknown keys
preserved); nearest-20 region selection when >20 location reminders.

**Contacts:** wire round-trip incl. unknown-key preservation; `GET` dispatch
(`q`/`name`/list); create stores server `id`; the §5B.1 removal path behaves as chosen.

## 11. Contract summary (must not get wrong)

1. **Bearer token** on every request; base URL configurable; Keychain storage.
2. **Reminders and Contacts are different models** — Reminders is offline-first LWW sync;
   Contacts is online REST CRUD with a read cache. Don't unify them.
3. **Reminders is buildable now; Contacts is BLOCKED** on the Gateway `/v1/contacts` router
   (§2) — build Reminders first, stub Contacts behind a flag.
4. Reminder: flat JSON, RFC 3339 UTC, `due` date-only vs timed by presence of `T`; **app
   generates the reminder UUID**; `updated_at`=now on every change; deletes soft
   (`deleted:true`); sync via `/v1/reminders/sync` (LWW + `rejected` + `since`).
5. Contact: **server assigns the `id`** (do not generate it); no `updated_at`/tombstones;
   mind the PATCH "can't clear a field" gap (§5B.1).
6. **Preserve unknown JSON keys** and round-trip them, both domains.
7. Reminders geofencing is **on-device**; names→coords via **`/v1/geocode`**, never
   `CLGeocoder`; respect the **20-region** cap (nearest-20).
