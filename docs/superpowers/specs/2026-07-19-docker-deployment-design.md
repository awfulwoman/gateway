# Containerize Gateway for deployment to the storage host

**Date:** 2026-07-19
**Status:** Approved
**Audience:** the developer implementing the change across the `gateway` and `infra`
repos. Assumes familiarity with Gateway's tool pattern (`init`/`register`, one module
per source) and infra's `composition-*` Ansible role convention.
Companion implementation plan: `docs/superpowers/plans/2026-07-19-docker-deployment.md`.

---

## 1. Why

Gateway runs today as a macOS launchd service (`system-mcp-gateway`) on **Malcolm** (Mac
mini), bound `0.0.0.0:4000`. That deployment mechanism is a one-off — every other
self-hosted service in this infra (`memorybank`, `chives`, `zfs-api`, …) is a Docker
container deployed via a `composition-*` Ansible role onto **server-64gb-storage**,
where Traefik, DNS registration, and ZFS-backed volumes are already wired up.

Moving Gateway onto that same pattern gets it: automatic HTTPS via Traefik, a proper
subdomain (`gateway.{{ domainname_infra }}` — which, notably, was referenced by `chives`
but had **no DNS record at all**, since Malcolm's launchd deployment never called
`network-register-subdomain`), GHCR-based image builds instead of a git-clone-and-`uv
sync` deploy, and one less host with bespoke config.

### Goals

- Run Gateway as a Docker container on `server-64gb-storage`, deployed the same way as
  `memorybank`/`chives`.
- Preserve every tool except Contacts (macOS-only, see below) with identical behavior.
- Reuse all existing vaulted secrets — no new secrets minted.
- Storage becomes the **sole** host; Malcolm's launchd deployment is retired.

### Non-goals

- Keeping Contacts working in the container. It depends on
  `pyobjc-framework-Contacts` (Apple's Contacts framework via PyObjC), which has no
  Linux equivalent. Dropping it is an accepted trade-off, not a v2 TODO.
- Changing the Google Calendar OAuth bootstrap flow. It stays a one-time,
  macOS-with-a-browser step; the resulting token is deployed as-is.
- Solving `vault_gateway_gcal_token_json` being undefined in the vault files (see §9) —
  a pre-existing gap unrelated to containerization, carried forward unchanged.

---

## 2. Decisions (locked)

These were confirmed with the user before implementation and drive every design choice
below:

1. **Obsidian vault access** — sync the `Charlie` vault onto the storage host with the
   existing [`system-obsidian-headless`](../../infra/roles/system-obsidian-headless)
   role (it already has an Ubuntu/systemd path via Obsidian Sync), then bind-mount the
   synced directory into the container read/write. Requires a one-time manual
   `ob login` on the storage host (MFA — not automatable).
2. **Malcolm** — decommission fully. Retire the `system-mcp-gateway` launchd role,
   migrate the canonical `reminders.db`, drop the macOS-only Contacts tool.
3. **Docs location** — this spec + its companion plan live in the `gateway` repo under
   `docs/superpowers/`.

---

## 3. Portability audit

| Tool group | Runtime dependency | Container-safe? |
|---|---|---|
| Calendar | Google Calendar API (OAuth token in env) | yes |
| Reminders | native SQLite file + geocode HTTP | yes (needs a volume) |
| Email | IMAP over network | yes |
| Obsidian (notes) | vault on filesystem; `grep` for search | yes (needs vault mount; `grep` ships in the base image) |
| Issues | same Obsidian vault | yes (same mount) |
| Karakeep | HTTP API | yes |
| OwnTracks | HTTP API | yes |
| **Contacts** | `pyobjc-framework-Contacts` (macOS only) | **no — gated out** |

Only Contacts blocks Linux. `Contacts` is already imported lazily *inside* each function
in `gateway/tools/contacts.py`, so importing the module is safe on Linux — only the
dependency install and tool *registration* need gating (see the plan for the exact
mechanism).

---

## 4. Deployment architecture

The container serves two HTTP surfaces on one port (4000), fronted by a **single**
Traefik router — no per-path routing is needed since each surface has its own in-app
auth:

- `/mcp` — streamable-HTTP MCP, bearer-auth via `GATEWAY_SERVER__AUTH_TOKENS`.
  Consumers: Claude Code, `chives`, the `gw` CLI.
- `/v1/*` — the native-Reminders JSON-HTTP API, its own token list
  `GATEWAY_REMINDERS__API_TOKENS`. Consumers: phone/iPad.

Config is entirely environment-driven (no baked-in paths), matching every other
`composition-*` app in this infra. Volumes:

- Reminders SQLite DB → a persistent volume under the composition's config dir.
- Obsidian vault → bind-mounted from the host path that `system-obsidian-headless`
  keeps synced.

**chives ↔ gateway**: both containers run on the same host and the same Docker bridge
network, so `chives` reaches `gateway` via internal DNS
(`http://gateway:4000/mcp`) rather than round-tripping through Traefik/TLS. The `/mcp`
bearer-auth requirement is unchanged either way (it's app-level middleware, not
network-scoped) — the auth key must still be supplied.

---

## 5. Container contract

- Base image: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (same base as `chives`,
  already proven in this infra). `bash` and `grep` are present, satisfying the
  Obsidian search fast-path and this repo's `docker-healthcheck` rule (`bash -c
  'echo > /dev/tcp/...'` — not `wget`/`curl`, which this slim image lacks).
- Built and pushed to `ghcr.io/awfulwoman/gateway` by CI on every push to `main`
  (mirrors `chives`' workflow).
- `GATEWAY_SERVER__HOST=0.0.0.0` is mandatory for the container (loopback-only would be
  unreachable from Traefik/other containers).
- `GATEWAY_SERVER__AUTH_TOKENS` must be set — Traefik exposes the host publicly, so the
  existing "auth disabled" warning path is not acceptable in this deployment.

---

## 6. Config & secrets

No new secrets. The container reuses every vault var the Malcolm deployment already
used (IMAP, Karakeep, OwnTracks, reminders tokens, the MCP bearer token, the Google
Calendar token JSON) — only the *paths* change (container-internal mount points instead
of host paths under `/opt/awfulwoman`).

---

## 7. Testing / acceptance

- `uv run pytest` stays green after gating Contacts (no test imports
  `gateway.tools.contacts` directly — only the CLI's HTTP-client-side command module,
  which never touches `pyobjc`).
- `docker build` on the target Dockerfile must not attempt to install
  `pyobjc-framework-Contacts` on Linux (verifies the platform marker took effect).
- A container run must boot and respond on `/mcp` without a Contacts-related crash.
- The rendered `docker-compose.yaml.j2` must validate under `docker compose config`.
- The new Ansible role must pass `ansible-lint` clean.

---

## 8. Contract summary (must not get wrong)

1. Contacts is unavailable in the container — this is intentional, not a bug.
2. `/mcp` and `/v1` share one port, one Traefik router; auth is per-surface, in-app.
3. All config arrives via env vars / mounts — nothing is baked into the image.
4. No new secrets — every vault var is reused, only mount/env paths change.
5. Storage is the **only** host after cutover; Malcolm's gateway deployment is fully
   retired, not left dormant.

---

## 9. Follow-up / out of scope

- **Pre-existing gap, not introduced by this work**: `system-mcp-gateway`'s (and now
  `composition-gateway`'s) `composition_gateway_gcal_token_json` default references
  `vault_gateway_gcal_token_json`, which is not defined anywhere in the vault files —
  only split `vault_gateway_gcal_client_id`/`_secret` exist. This means Google Calendar
  was already broken on the Malcolm deployment; carried forward unchanged since fixing
  the OAuth wiring is unrelated to containerization.
- Contacts on Linux — would require a networked macOS Contacts bridge; not planned.
- `reminders.db` migration and the DNS cutover from Malcolm to storage are one-time
  operational steps during rollout, not code changes — see the plan's Verification
  section.
