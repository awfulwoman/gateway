# Reminders iOS app — build handoff

**Date:** 2026-07-18
**Status:** Cancelled
**Audience:** the agent/developer building the iOS app, in a **new, separate
project**. This document is **self-contained** — you do not need the Gateway
repository or any prior app ("NowThis") to build against it. Everything about the
wire protocol the app depends on is reproduced here.

---

## 1. What you are building

A personal reminders app for iOS. One user (the owner). It stores reminders
locally and syncs them to a **self-hosted "Gateway" server** over plain
JSON-over-HTTPS. It fires **time-based** local notifications and **location-based**
(geofence) notifications entirely on-device.

Explicit non-features (the whole point of this project):

- **No cloud services.** No iCloud, no Apple Reminders/EventKit, no CalDAV, no
  third-party backend. The only network peer is the owner's Gateway server.
- **No Apple geocoding.** Place-name → coordinates is done by asking Gateway
  (`GET /v1/geocode`), not `CLGeocoder`.

The app is **offline-first**: the local store is the source of truth for the UI;
sync reconciles it with the server in the background. You can build and exercise
the entire app against a Gateway instance reachable at a configurable base URL.

### v1 scope

- Browse reminders, grouped by list.
- Create / edit / complete / delete a reminder (title, notes, due date/time,
  priority, list, optional location geofence).
- Time notifications and location (arrive/leave) notifications.
- Settings: server base URL + auth token.
- Background + foreground sync.

### Out of scope for v1

Subtasks/nesting, recurrence, sharing/multi-user, multiple accounts,
App Intents/Siri, real-time push. (The protocol reserves room for subtasks and
recurrence; see §3.) A simple read-only home/lock-screen **widget is in scope** —
see §9.1.

---

## 2. Connection & auth

- **Base URL**: a full URL the owner enters in Settings, e.g.
  `https://gateway.example.com` — the API lives under `/v1` on that host. Do not
  hardcode; store it.
- **Auth**: every request carries `Authorization: Bearer <token>`. The token is a
  fixed secret the owner pastes in Settings (one token per device, so it can be
  revoked independently). Store base URL + token in the **Keychain**.
- **Transport**: HTTPS only (TLS terminated by the server's reverse proxy).
- A missing/invalid token returns **401** — surface this as "check your server URL
  and token" in the UI.

First-run onboarding: a screen to enter base URL + token, then a test call
(`GET /v1/reminders`) to confirm connectivity before proceeding.

---

## 3. The reminder object (wire format)

A reminder is a **flat JSON object**. All timestamps are **RFC 3339 UTC** with a
`Z` suffix (e.g. `2026-07-18T09:15:04Z`).

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
| `id` | string (UUID) | Stable identity. **The app generates it** (`UUID().uuidString`) when creating a reminder, and never changes it. |
| `title` | string | Required, non-empty. |
| `notes` | string \| null | Free text. |
| `due` | string \| null | **`YYYY-MM-DD`** = all-day; the app notifies at **09:00 local time** on that date (see §7). **Full RFC 3339** (has a `T`) = a specific time. The presence of `T` is the only signal — there is no separate all-day flag. |
| `priority` | int | `0` none · `1` high · `5` medium · `9` low. (Map to a 4-tier UI: none/high/medium/low.) |
| `list` | string | List/group name, e.g. `"Reminders"`, `"Shopping"`. Lists are **implicit**: a list exists because a reminder names it. Default new reminders to `"Reminders"`. No separate list resource. |
| `done` | bool | Completion. |
| `completed_at` | string \| null | Set to "now" when `done` goes true; set null when it goes false. |
| `location` | object \| null | Geofence, or null for none. See below. |
| `created_at` | string | Set once at creation; never modified. |
| `updated_at` | string | **Critical for sync.** Set to the writer's current UTC time on *every* edit (including completing and deleting). Drives conflict resolution. |
| `deleted` | bool | Tombstone flag. Deletes are soft — you send `deleted:true`, you don't drop the row. |

**`location` object:** `lat`/`lon` are authoritative and always present when
`location` is set. `name` is an optional human label for display. `radius_m` is
the geofence radius in metres (default 150 if you create one without asking).
`trigger` is `"arrive"` or `"leave"`.

**Forward-compat rule:** the server may add fields later. **Preserve and
round-trip any JSON keys you don't recognise** — decode into your model, keep the
originals, and send them back on `PUT`. Do not drop unknown keys. `parent_id` and
`rrule` are reserved for future subtasks/recurrence: in v1 treat them **exactly as
unknown keys** — do not model or act on them, keep them in `extraJSON` (§6), and
round-trip them unchanged. The rule is general: *any* key you decode but do not
store in a first-class field goes into `extraJSON` and comes back out on encode.

---

## 4. HTTP API

Base: `{baseURL}/v1`. All bodies `application/json`. All requests need the bearer
header. Errors look like `{"error": {"code": "...", "message": "..."}}`.

### 4.1 Endpoints

| Method & path | Body | Returns |
|---|---|---|
| `GET /v1/reminders` | — | `{ "server_time": "…Z", "reminders": [ …objects… ] }` — **the full set, including tombstones** (`deleted:true`). |
| `GET /v1/reminders?since=<RFC3339>` | — | Same shape, but only objects whose `updated_at` is **strictly greater than** `since` (still includes tombstones). |
| `PUT /v1/reminders/{id}` | one full reminder object | `200` + the stored object on success. `409` + `{ "current": <object> }` if your write is **stale** (server has a newer `updated_at`). `400` on validation error. |
| `DELETE /v1/reminders/{id}` | optional `{ "updated_at": "…Z" }` | `200` + the tombstone object. (Equivalent to `PUT` with `deleted:true`.) |
| `POST /v1/reminders/sync` | `{ "since": "…Z" \| null, "changes": [ …objects… ] }` | `200` + `{ "server_time", "reminders", "rejected" }` — see §5. **This is the endpoint the app should use for normal sync.** |
| `GET /v1/geocode?q=<text>` | — | `{ "name", "lat", "lon" }` (best match) or `404`. |
| `GET /v1/geocode?lat=<n>&lon=<n>` | — | `{ "name", "lat", "lon" }` (reverse) or `404`. |

### 4.2 Status codes

`200` ok · `400` validation (e.g. empty title, or a `location.name` the server
couldn't geocode) · `401` bad/missing token · `404` unknown route / no geocode
match · `409` stale write (body carries the winning `current` object).

### 4.3 `POST /v1/reminders/sync` example

Request:

```json
{
  "since": "2026-07-18T09:00:00Z",
  "changes": [
    { "id": "abc…", "title": "Milk", "done": true,
      "completed_at": "2026-07-18T09:19:00Z",
      "updated_at": "2026-07-18T09:19:00Z", "created_at": "2026-07-17T…Z" }
  ]
}
```

Response:

```json
{
  "server_time": "2026-07-18T09:20:11Z",
  "reminders": [ { "id": "def…", "title": "Call plumber", "updated_at": "2026-07-18T09:12:00Z", … } ],
  "rejected": [ { "id": "ghi…", "current": { …the server's newer object… } } ]
}
```

- `reminders` = every object changed **server-side** since `since` (after applying
  your `changes`), including tombstones. Apply them to your local store.
- `rejected` = the pushes the server **declined** because it already held a newer
  `updated_at`. Replace your local copy with each `current` and clear its dirty
  flag — this device lost that race.

---

## 5. Sync algorithm (implement exactly)

**Model:** whole-object **last-write-wins (LWW)** keyed on `updated_at`. There is
no per-field merge and no version vector. The larger `updated_at` wins, always —
including deletes (a later delete beats an earlier edit; a later edit resurrects an
earlier tombstone). This is deliberately simple; it's a single-user system.

**Writer rule:** whenever the app changes a reminder in any way (edit, complete,
delete), it sets that reminder's `updated_at` to `Date()` in UTC **before** saving
locally and marks it **dirty** (needs push).

**A sync cycle:**

1. `POST /v1/reminders/sync` with:
   - `since` = the `server_time` string persisted from the last successful sync
     (or `null` on the very first sync → server returns everything).
   - `changes` = all locally-dirty reminders (full objects).
2. For every object in the response `reminders`, apply LWW to the local store:
   replace the local copy **iff** the incoming `updated_at` is newer than the local
   one (or the local one doesn't exist). Tombstones (`deleted:true`) that win are
   applied by removing the reminder from the UI (keep or hard-delete the local row
   as you prefer, but stop showing/monitoring it).
3. For every entry in `rejected`, overwrite the local copy with `current` and clear
   its dirty flag.
4. Clear the dirty flag on any pushed change that was **not** rejected.
5. Persist `server_time` as the new `since`.

**Conflict handling** falls out of the above — no special code beyond the LWW
comparison and the `rejected` handling.

**First sync / recovery:** `since = null` pulls the full set. If the app has been
offline a long time (server GCs tombstones after ~30 days, so a very old `since`
could miss a delete), doing a `since = null` full pull is always a safe reset — do
it on first launch and any time you detect the local store may be stale (e.g. after
a restore).

**Caveat to accept, not solve:** LWW uses device wall-clocks. Gross clock skew can
pick a surprising winner. Single user + NTP makes this a non-issue; do not build
vector clocks.

**When to sync:** on app foreground; on pull-to-refresh; after a local edit
(debounce a few seconds, then push); and from a background task (see §8). No server
push exists — the app always initiates.

---

## 6. Local data model

Use SwiftData (or Core Data). The local model **is** the protocol object plus a
few local-only fields. The store is the UI's single source of truth.

Suggested model:

```
Reminder
  id: String            // UUID, == wire id, primary key
  title: String
  notes: String?
  due: Date?
  dueIsDateOnly: Bool   // derived from wire format on decode; controls "end of local day"
  priority: Int         // 0/1/5/9
  list: String
  done: Bool
  completedAt: Date?
  // location (flatten or a small embedded type)
  locName: String?; locLat: Double?; locLon: Double?; locRadiusM: Int?; locTrigger: String?
  createdAt: Date
  updatedAt: Date       // the LWW key
  deleted: Bool

  // local-only, never sent:
  dirty: Bool           // has unpushed local changes
  extraJSON: Data?      // verbatim keys with no first-class field above (incl. parent_id, rrule),
                        // re-merged on encode (forward-compat)
```

Encode/decode helpers convert between this and the wire JSON, including:
`due` date-only vs timed (emit `YYYY-MM-DD` vs full RFC 3339); RFC 3339 UTC for all
timestamps; `location` ⇄ the flat `loc*` fields; merge `extraJSON` back in on
encode.

**Put the store in an App Group container** (`group.<your-bundle-id>`) so the
widget extension (§9.1) can read it. Configure the SwiftData `ModelContainer` (or
Core Data store) with that shared URL from the start — retrofitting later is
painful. The main app is the only writer; the widget reads.

---

## 7. Notifications & geofencing

Request permissions up front (or on first use): **notifications**
(`UNUserNotificationCenter`) and **location Always** (region monitoring requires
Always authorization; explain why in the prompt).

### Time reminders

For each non-done reminder with a `due`, schedule a
`UNCalendarNotificationTrigger`. For a date-only `due`, fire at **09:00 local time
on the due date** (the fixed v1 default; a user-configurable time is out of scope).
Reschedule on edit; cancel on complete/delete.

### Location reminders (on-device geofencing)

- For each non-done reminder with a `location`, register a `CLCircularRegion`
  (`center` = lat/lon, `radius` = `radius_m`) via `CLLocationManager`.
- Set `notifyOnEntry` / `notifyOnExit` from `trigger` (`arrive` → entry,
  `leave` → exit).
- On the region event, fire a local `UNNotification` ("📍 <title>"). The reminder
  is **not** auto-completed — the owner completes it manually.
- **iOS monitors at most 20 regions.** If there are more than 20 active location
  reminders, monitor the **20 nearest** to the current location and re-evaluate the
  set on significant-location-change (`startMonitoringSignificantLocationChanges`).
- Remove a region when its reminder is completed, deleted, or loses its location.

### Getting coordinates without Apple

When the owner sets a location by typing a place name (not dropping a map pin),
resolve it via `GET /v1/geocode?q=<text>` and store the returned `lat`/`lon`
(and `name`). Do **not** use `CLGeocoder`. A map-pin drop can use the raw
coordinates directly (optionally reverse-geocode via `GET /v1/geocode?lat=&lon=`
for a display name).

---

## 8. Background sync

- Register a `BGAppRefreshTask` to run a sync cycle periodically so notifications
  and geofences reflect server-side changes made from other devices / the CLI.
- Also sync on `didFinishLaunching` / foreground and on pull-to-refresh.
- Keep background work short: one `POST /v1/reminders/sync`, apply results,
  reconcile scheduled notifications and monitored regions, done.

---

## 9. UI (v1, minimal)

- **List screen**: reminders grouped by `list`; incomplete first; show title, due,
  priority indicator, a 📍 marker for location reminders; swipe/tap to complete;
  swipe to delete.
- **Editor**: title, notes, due (date, with an all-day toggle → controls date-only
  vs timed), priority picker, list picker (free text / pick existing), optional
  location (search field → `/v1/geocode`, or map pin) with radius + arrive/leave.
- **Settings**: server base URL, token (both to Keychain), a "test connection"
  button, and manual "sync now".

Keep it plain and native. No design system required.

### 9.1 Widget (WidgetKit)

A simple, **read-only** widget showing upcoming reminders. Read-only keeps it
trivial — no App Intents, no completing from the widget in v1.

- **Extension target** in the same App Group as the app (§6); the widget's
  `TimelineProvider` reads the shared local store directly. **It does not make
  network calls** — it only reflects whatever the last app sync wrote.
- **Content**: the next incomplete, non-deleted reminders, sorted by due
  (soonest first; undated last), then priority. Show title + a short due label
  (e.g. "Today", "Tomorrow", "Fri", or "—"); a 📍 glyph for location reminders.
- **Families**:
  - `systemSmall`: count of reminders due today + the single next one.
  - `systemMedium`: the next ~3–4 reminders as a list.
  - (Optional) `accessoryRectangular` lock-screen: next reminder + count.
- **Timeline**: a single entry for "now" plus a refresh at the next due boundary
  (e.g. start of next day) so relative labels stay correct; otherwise rely on
  explicit reloads.
- **Refresh**: after every successful sync cycle the app calls
  `WidgetCenter.shared.reloadAllTimelines()` so the widget reflects server-side
  changes. Also reload after a local edit.
- **Tap**: opens the app (a deep link to the relevant list is a nice-to-have, not
  required).
- **Empty state**: "No reminders" / "All done".

---

## 10. Acceptance / verification

Point the app at a running Gateway (the owner can run one locally with a known
token). Verify:

1. **Onboarding**: wrong token → 401 surfaced; correct token → `GET /v1/reminders`
   succeeds.
2. **Create** a reminder in the app → it appears server-side (owner checks via
   `curl` or the `gw` CLI) after a sync.
3. **Edit on the server** (e.g. `curl`/CLI changes a title) → app shows the change
   after a sync.
4. **Conflict**: edit the same reminder on server and app while app is offline;
   on reconnect, the newer `updated_at` wins and the loser adopts the winner (check
   the `rejected` path when the app is the loser).
5. **Complete / delete** round-trips both directions; tombstones remove the item
   from the app.
6. **Time notification** fires at the due time (and date-only behaves as
   documented).
7. **Location notification**: set a geofence at a nearby place; crossing it fires a
   notification. Simulate with Xcode's location simulation if needed.
8. **Offline**: create/edit offline, then reconnect → changes push.
9. **Widget**: add the widget → it shows upcoming reminders; after a sync that
   changes/adds/completes a reminder, the widget updates (reflects the shared
   store, no separate network call).

### Protocol conformance unit tests (write these)

- LWW: incoming newer replaces local; incoming older is ignored; equal is a no-op.
- `rejected` handling: local copy replaced by `current`, dirty cleared.
- Tombstone wins → item removed and its region/notification cancelled.
- `since` continuity: after applying a sync, the stored `since` == returned
  `server_time`.
- Wire round-trip: date-only vs timed `due`; location ⇄ flat fields; unknown keys
  preserved through decode→encode.
- Nearest-20 region selection when >20 location reminders exist.

---

## 11. Summary of the contract (the parts you must not get wrong)

1. **Bearer token** on every request; base URL configurable; Keychain storage.
2. Reminder is **flat JSON**, timestamps **RFC 3339 UTC**, `due` date-only vs timed
   by the presence of `T`.
3. App **generates the UUID `id`**; sets `updated_at`=now on every change; deletes
   are **soft** (`deleted:true`).
4. Sync = `POST /v1/reminders/sync` with `since` + dirty `changes`; apply returned
   `reminders` by **LWW**; adopt `rejected[].current`; persist `server_time` as next
   `since`; `since=null` for a full pull.
5. **Preserve unknown JSON keys** and round-trip them.
6. Geofencing is **on-device**; names→coords via **`/v1/geocode`**, never
   `CLGeocoder`; respect the **20-region** cap (nearest-20).
```
