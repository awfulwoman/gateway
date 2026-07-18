# Location-based reminders via OwnTracks geofencing + HA notifications

## Context

NowThis failed as the geofencing client for Radicale-backed reminders, and research showed **no** iOS task app does CalDAV-synced geofencing. Instead of hunting for one, we use the geofencing engine already on the phone: **OwnTracks iOS** (region monitoring + MQTT transition events). The task app becomes optional.

Flow: `create_reminder(location_name=...)` → forward-geocode via the **already-deployed** Nominatim (`composition-nominatim` on server-64gb-storage) → store VTODO in Radicale with a standard **RFC 9074 `VALARM;PROXIMITY`** → publish an OwnTracks `setWaypoints` command over MQTT (broker is anonymous, `mqtt.<domain>:1883`) → phone monitors region on-device → on enter/leave, phone publishes a `transition` event → a new tiny subscriber service on homebrain matches it and fires a push via the **Home Assistant** REST API (companion app). Deterministic trigger, no LLM — allowed per gateway CLAUDE.md's clarified constraint.

Decisions already made with Charlie: notifications via HA companion app; subscriber as a new infra role; Python for the subscriber script (her stated script preference).

---

## Part 1 — Gateway repo (`~/Code/awfulwoman/gateway`)

### 1.1 Config (`gateway/config.py`)
- New `NominatimConfig(BaseModel)`: `base_url: str = ""` → env `GATEWAY_NOMINATIM__BASE_URL`.
- Extend `OwnTracksConfig`: add `mqtt_host: str = ""`, `mqtt_port: int = 1883` (waypoint publishing; existing `owntracks_user`/`owntracks_device` name the target topic).
- Add `nominatim: NominatimConfig = NominatimConfig()` to `Config`.

### 1.2 New module `gateway/tools/geocode.py`
Follow the `init(config)/register(mcp)` pattern from `main.py` (mirror of `owntracks.py`'s httpx style; the vikunja plan doc `docs/superpowers/plans/2026-06-07-vikunja-integration.md` is the worked example for adding a module).
- `geocode(query) -> dict` — GET `{base}/search?q=&format=jsonv2&limit=1` → lat, lon, display_name.
- `reverse_geocode(lat, lon) -> dict` — GET `{base}/reverse?lat=&lon=&format=jsonv2` → address.
- Register both as MCP tools (`geocode_place`, `reverse_geocode`) — this delivers the original "reverse geocoding for OwnTracks data" goal too.
- Wire into `main.py` (`geocode.init(config.nominatim)` + `register`).

### 1.3 OwnTracks waypoint publishing (`gateway/tools/owntracks.py`)
- New dep: `paho-mqtt` in `pyproject.toml` (sync one-shot publish).
- `publish_waypoint(desc, lat, lon, radius_m, tst) -> None`: publish to `owntracks/<user>/<device>/cmd`:
  ```json
  {"_type":"cmd","action":"setWaypoints","waypoints":{"_type":"waypoints",
    "waypoints":[{"_type":"waypoint","desc":desc,"lat":lat,"lon":lon,"rad":radius_m,"tst":tst}]}}
  ```
  `tst` is the waypoint's stable ID (unix seconds at creation).
- `disable_waypoint(desc, lat, lon, tst)`: republish same `tst` with `rad: 0` (rad ≤ 0 = unmonitored POI) — OwnTracks has no remote delete.
- Waypoint `desc` format (the contract with the subscriber): `reminder[arrive]: <title>` / `reminder[leave]: <title>`.

### 1.4 Reminders (`gateway/tools/reminders.py`)
- `create_reminder`: add `radius_m: int = 150`. When `location_name` set:
  1. `geocode.geocode(location_name)`; on failure return an error dict (don't silently create without a geofence).
  2. In `_build_vtodo_ical`, replace the `[location: ...]` text marker with a real RFC 9074 alarm inside the VTODO:
     ```
     BEGIN:VALARM
     UID:<uuid>@gateway
     ACTION:DISPLAY
     TRIGGER;VALUE=DATE-TIME:19760401T005545Z   ; required but ignored per RFC 9074 §8
     DESCRIPTION:<title>
     PROXIMITY:ARRIVE|DEPART                    ; arrive→ARRIVE, leave→DEPART
     BEGIN:VLOCATION
     UID:<uuid>@gateway
     URL:geo:<lat>,<lon>;u=<radius_m>
     END:VLOCATION
     END:VALARM
     ```
     (icalendar lib: `todo.add_component()` with a generic `Component` named VALARM/VLOCATION if no typed class.)
  3. Add `X-GATEWAY-WAYPOINT-TST:<tst>` + `X-GATEWAY-WAYPOINT-GEO:<lat>,<lon>` on the VTODO so completion can disarm the waypoint.
  4. `owntracks.publish_waypoint(...)`.
- `_todo_to_dict`: parse VALARM/PROXIMITY back out into a `location` field (replaces reading the old text marker).
- `complete_reminder` / `delete_reminder`: if the matched VTODO carries `X-GATEWAY-WAYPOINT-TST`, call `disable_waypoint` before completing/deleting.

### 1.5 CLI (`gateway/cli/commands/reminders.py`, `gateway/cli/__init__.py`, `gateway/cli/fmt.py`)
- `reminders create`: add `--radius` option; existing `--location`/`--arrive-or-leave` unchanged.
- New `gw geocode <query>` / `gw geocode --reverse LAT LON` command group for the new tools.
- `fmt.py` reminders formatter: show `location` field when present.

### 1.6 Tests (`tests/test_reminders.py` style — hand-written fakes + monkeypatch)
- Extend the existing `calendars` fixture flow; monkeypatch `geocode.geocode` (fixed lat/lon) and `owntracks.publish_waypoint` (capture calls).
- Replace `test_create_reminder_with_location_stores_note` with: VALARM present with correct PROXIMITY + `geo:` URI; waypoint published with matching desc/tst; X-props stored; complete/delete disarms waypoint; geocode failure surfaces an error.
- New `tests/test_geocode.py` with httpx mocked (monkeypatch style).

## Part 2 — Infra repo (`~/Code/awfulwoman/infra`)

### 2.1 Gateway env (`roles/system-mcp-gateway/templates/env.j2` + `defaults/main.yaml`)
- `GATEWAY_NOMINATIM__BASE_URL=https://nominatim.{{ domainname_infra }}`
- `GATEWAY_OWNTRACKS__MQTT_HOST=mqtt.{{ domainname_infra }}` (anonymous broker, no creds).

### 2.2 New role `system-owntracks-notify` (deployed on **minipc-8gb-homebrain**, where MQTT + HA live)
Model on `roles/system-mqtt2cmd/` (script + systemd unit + defaults), but Python:
- `templates/owntracks-notify.py.j2`: paho-mqtt (apt `python3-paho-mqtt`) client, `loop_forever` with auto-reconnect, subscribed to `owntracks/+/+/event`. On `_type == "transition"` whose `desc` matches `^reminder\[(arrive|leave)\]: (.+)$` and whose `event` matches (arrive→`enter`, leave→`leave`): POST `http://localhost:8123/api/services/notify/{{ owntracks_notify_ha_service }}` with `Authorization: Bearer {{ vault_homeassistant_token }}`, body `{"title": "📍 Reminder", "message": <title>}` (urllib, stdlib). Log to stdout → journald.
- `templates/owntracks-notify.service`: simple systemd unit like `mqtt2cmd.service`.
- `defaults/main.yaml`: `owntracks_notify_broker: localhost` (mosquitto publishes 1883 on host), `owntracks_notify_ha_url: http://localhost:8123`, `owntracks_notify_ha_service: mobile_app_<charlie's phone>` (confirm exact service name at deploy time), token mapped from vault var.
- New vault secret: `vault_homeassistant_token` in `inventory/host_vars/minipc-8gb-homebrain/vault_homeassistant.yaml` (ansible-vault, identity `beanpod`, same pattern as `vault_nominatim.yaml`).
- Add role to `playbooks/hosts/minipc-8gb-homebrain/core.yaml` with a tag.

### 2.3 Manual / out-of-band steps (Charlie)
1. Create an HA long-lived access token (HA profile UI) → vault-encrypt into `vault_homeassistant.yaml`; confirm the HA notify service name for her iPhone.
2. OwnTracks iOS: enable remote commands (`cmd` setting) so `setWaypoints` is honoured.

## Order of work
1. Gateway: geocode module + config + tests → 2. Gateway: VALARM + waypoint publish in reminders + tests → 3. Infra: env.j2 additions + `system-owntracks-notify` role → 4. Deploys (gateway per `.claude/rules/deploy.md` on malcolm; homebrain core playbook for the new role) → 5. End-to-end verification.

## Verification
- Unit: `uv run pytest` in gateway repo.
- Geocoding live: `gw geocode "some local place"` against deployed Nominatim.
- Create: `gw reminders create "Test compost" --location "<real place>"`; then inspect raw VTODO in Radicale (curl the .ics) for VALARM/PROXIMITY + X-props; confirm waypoint appears in OwnTracks iOS app.
- Trigger without leaving the house: publish a synthetic transition to `owntracks/charlie/iphone/event` (`mosquitto_pub`, `{"_type":"transition","event":"enter","desc":"reminder[arrive]: Test compost",...}`) → HA push arrives on phone. Journalctl on homebrain shows the match.
- Real-world: one actual geofence crossing.
- Cleanup check: `gw reminders complete "Test compost"` → waypoint disarmed (rad 0 republished).

## Non-goals / notes
- NowThis↔Radicale sync bug: not addressed here; app becomes optional. Diagnose separately if she still wants it as a viewer.
- Disarmed (rad=0) waypoints accumulate as POIs in the OwnTracks app list; occasional manual cleanup in-app is acceptable.
- Radicale stores the VALARM verbatim (protocol-agnostic) — no server changes needed.
- Privacy: proximity alarms encode intent+location, but everything stays on self-hosted services.
