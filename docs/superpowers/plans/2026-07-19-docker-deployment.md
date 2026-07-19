# Spec: Containerize Gateway and deploy to the storage host

Status: draft / planning
Owner: Charlie
Scope: two repos — `gateway` (image + code changes) and `infra` (deploy role + host wiring)

## Goal

Move Gateway off its macOS launchd deployment on **Malcolm** (Mac mini) and run it as
a Docker container on **server-64gb-storage**, deployed the same Ansible-`composition-*`
way as `memorybank` and `chives`. Storage becomes the **sole** host. The macOS-native
Contacts tool is dropped (accepted trade-off).

## Decisions (locked)

1. **Obsidian vault access** — sync the `Charlie` vault onto the storage host with the
   existing [`system-obsidian-headless`](../../infra/roles/system-obsidian-headless)
   role (Ubuntu/systemd path via Obsidian Sync), and bind-mount it into the container.
   Requires the documented one-time manual `ob login` on the host.
2. **Malcolm** — decommission. Retire the `system-mcp-gateway` launchd role from
   Malcolm's playbook; migrate the canonical `reminders.db`; Contacts is lost.
3. **Spec location** — this file, in the gateway repo.

## What currently runs (baseline)

- Deployed by `infra` role `system-mcp-gateway` as launchd `com.awfulwoman.gateway` on
  Malcolm, `uv run gateway --transport http`, bound `0.0.0.0:4000`.
- Serves two surfaces on one port:
  - `/mcp` — streamable-HTTP MCP, bearer-auth via `GATEWAY_SERVER__AUTH_TOKENS`
    (consumers: Claude Code, `chives`, the `gw` CLI).
  - `/v1/*` — reminders JSON-HTTP API, its own token list
    `GATEWAY_REMINDERS__API_TOKENS` (consumers: phone/iPad).
- `chives` already targets `https://gateway.{{ domainname_infra }}/mcp` (commented in
  `composition-chives` defaults) — so the target hostname is already the intended one.

## Portability audit

| Tool group | Runtime dependency | Container-safe? |
|---|---|---|
| Calendar | Google Calendar API (OAuth token in env) | yes |
| Reminders | native SQLite file + geocode HTTP | yes (needs a volume) |
| Email | IMAP over network | yes |
| Obsidian (notes) | vault on filesystem; `grep` for search | yes (needs vault mount; `grep` present in base image) |
| Issues | same Obsidian vault | yes (same mount) |
| Karakeep | HTTP API | yes |
| OwnTracks | HTTP API | yes |
| **Contacts** | `pyobjc-framework-Contacts` (macOS only) | **no — gated out** |

Only Contacts blocks Linux. `Contacts` is already imported lazily *inside* each
function in `gateway/tools/contacts.py`, so importing the module is safe on Linux — only
the dependency install and tool registration need gating.

---

## Part A — `gateway` repo changes

### A1. Gate the Contacts tool to macOS

- **`pyproject.toml`**: add a platform marker so `uv sync` doesn't try to install a
  macOS-only wheel on Linux:
  ```toml
  "pyobjc-framework-Contacts>=10 ; sys_platform == 'darwin'",
  ```
  Re-run `uv lock` and commit the updated `uv.lock` (it records the marker).
- **`gateway/main.py`**: make registration conditional. Keep the module import (it's
  lazy) or drop it from the top-level import; either way, guard registration:
  ```python
  import sys
  ...
  if sys.platform == "darwin":
      from gateway.tools import contacts
      contacts.register(mcp)
  ```
  Result: on Linux the container starts with 38 tools (Contacts' 3 absent); on macOS
  dev machines behavior is unchanged.

### A2. Dockerfile

Model on `chives/Dockerfile` (uv base image, two-stage sync for layer caching):

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Deps first for caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY gateway/ ./gateway/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 4000

CMD ["python", "-m", "gateway.main", "--transport", "http"]
```

Notes:
- `grep` ships in `bookworm-slim`, so Obsidian search's fast path works.
- The reminders DB path and vault path come entirely from env / mounts (below), not
  baked in.

### A3. `.dockerignore`

Add (model on chives): exclude `.venv/`, `.git`, `tests/`, `.pytest_cache/`, `logs/`,
`*.db`, `.env`, `__pycache__/`, `docs/`, `scripts/`.

### A4. CI: build + push image to GHCR

Add `.github/workflows/docker.yml`, copied from `chives/.github/workflows/docker.yml`
(builds on push to `main`, pushes `ghcr.io/awfulwoman/gateway:latest` + `:<sha>`). No
changes needed beyond the repo name resolving automatically via `github.repository`.

### A5. Bind address

No code change — driven by env. Container must run with `GATEWAY_SERVER__HOST=0.0.0.0`
(Malcolm already sets this). Auth on `/mcp` stays mandatory since Traefik exposes the
host; `GATEWAY_SERVER__AUTH_TOKENS` must be set (a startup warning fires if empty).

### A6. Docs

Update `README.md`: add a "Running in Docker" section and note Contacts is macOS-only
(unavailable in the container).

---

## Part B — `infra` repo changes

### B1. New role `composition-gateway`

Model on `composition-chives` (closest analog — Python, config + state volumes, Traefik,
healthcheck). Files:

- `meta/main.yaml` → depends on `composition-common` with `composition_name: gateway`.
- `defaults/main.yaml` → all the vars currently in `system-mcp-gateway/defaults`
  (IMAP, GCal token, Karakeep, OwnTracks, reminders tokens, server auth tokens), reusing
  the same vault vars so no new secrets are minted.
- `templates/environment_vars.j2` → the same `GATEWAY_*` keys as
  `system-mcp-gateway/templates/env.j2`, but with container paths:
  - `GATEWAY_SERVER__HOST=0.0.0.0`
  - `GATEWAY_SERVER__PORT=4000`
  - `GATEWAY_OBSIDIAN__VAULT_PATH=/vault` (bind-mounted)
  - `GATEWAY_REMINDERS__DB_PATH=/data/reminders.db` (volume)
- `templates/docker-compose.yaml.j2`:
  ```yaml
  name: "{{ composition_name }}"
  services:
    gateway:
      container_name: "{{ composition_name }}"
      image: ghcr.io/awfulwoman/gateway:latest
      restart: unless-stopped
      env_file: .environment_vars
      volumes:
        - "{{ composition_config }}/db:/data"
        - "{{ obsidian_vault_path_on_host }}:/vault"
        - /etc/localtime:/etc/localtime:ro
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.{{ composition_name }}.rule=Host(`{{ composition_name }}.{{ domainname_infra }}`)"
        - "traefik.http.routers.{{ composition_name }}.tls=true"
        - "traefik.http.routers.{{ composition_name }}.tls.certresolver=letsencrypt"
        - "traefik.http.services.{{ composition_name }}.loadbalancer.server.port=4000"
      networks:
        - "{{ default_docker_network }}"
      healthcheck:
        test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/localhost/4000'"]
        interval: 30s
        timeout: 10s
        retries: 3
        start_period: 30s
  networks:
    "{{ default_docker_network }}":
      external: true
  ```
  A single Traefik router for `gateway.{domain}` fronts **both** `/mcp` and `/v1` (same
  port) — no per-path routing needed. `/mcp` and `/v1` keep their own in-app bearer/token
  auth.
- `tasks/main.yaml` → template compose + `.environment_vars` + create `db` dir, register
  subdomain via `network-register-subdomain`, `docker_compose_v2` with `pull: always`,
  notify Restart Traefik (all as in `composition-chives`).

### B2. Obsidian vault on the storage host

- Add the storage host to `system-obsidian-headless` with the `Charlie` vault (reuse the
  `system_obsidian_headless_vaults` block from Malcolm's host_vars; the role already has
  an Ubuntu/systemd path).
- **Manual one-time**: `ob login` on the storage host before the first role run (MFA —
  not automatable, documented in the role's README).
- Point the compose bind mount at the synced vault path (the role's configured vault
  path on the host).

### B3. Reminders DB migration

Preserve existing reminders data (device state + reminders) rather than starting fresh:

1. Stop the Malcolm gateway.
2. `scp` Malcolm's `reminders.db` →
   `{{ composition_config }}/db/reminders.db` on storage.
3. Start the storage container (which then owns the canonical DB).

Device `GATEWAY_REMINDERS__API_TOKENS` stay identical (same vault var), so phone/iPad
clients keep working once `gateway.{domain}` points at storage.

### B4. Wire into the storage host playbook

Add to `playbooks/hosts/server-64gb-storage/core.yaml`:
```yaml
  - role: system-obsidian-headless    # if not already present
  - role: composition-gateway
    tags: [composition, gateway, composition-gateway]
```
(Consider a dedicated `playbooks/hosts/server-64gb-storage/gateway.yaml` mirroring the
existing per-service playbooks like `memorybank.yaml`.)

### B5. Decommission Malcolm

- Remove the `system-mcp-gateway` role and its vars from
  `playbooks/hosts/apple-macmini-m4-16gb-malcolm/core.yaml` and host_vars.
- Add a one-shot teardown (or manual step): `launchctl bootout` +
  remove `com.awfulwoman.gateway.plist` on Malcolm.
- `system-mcp-gateway` role can be deleted from the repo once no host references it
  (or kept dormant — prefer deletion to avoid drift).

### B6. DNS / routing

`gateway.{{ domainname_infra }}` currently resolves to Malcolm. After cutover it must
resolve to the storage host's Traefik. `network-register-subdomain` (invoked by the new
role) handles the record; verify the old Malcolm record is removed/updated so there's no
split resolution.

---

## Consumers after cutover

- **chives** — uncomment/point `composition_chives_mcps` at
  `https://gateway.{{ domainname_infra }}/mcp` with `vault_gateway_mcp_token`. (Or, since
  both run on the storage Docker network, `http://gateway:4000/mcp` internally — avoids a
  Traefik round-trip. Pick one; internal is simpler and needs no TLS.)
- **`gw` CLI** — runs on the Mac; set `GATEWAY_URL=https://gateway.{{ domainname_infra }}/mcp`
  and `GATEWAY_TOKEN=<vault_gateway_mcp_token>`. No change if it already targets that host.
- **Phone/iPad reminders** — hit `https://gateway.{{ domainname_infra }}/v1/...`
  unchanged; tokens preserved.
- **Claude Code** — MCP registration URL unchanged (`gateway.{domain}/mcp`).

## Out of scope

- Contacts tool on Linux (dropped; would require a networked macOS Contacts bridge).
- Google Calendar OAuth bootstrap (`gcal_auth`) — remains a one-time macOS-with-browser
  step; the resulting token in `vault_gateway_gcal_token_json` is reused as-is.

## Rollout order

1. gateway repo: A1–A4, merge → CI publishes `ghcr.io/awfulwoman/gateway:latest`.
2. infra: B2 (vault sync + `ob login`) on storage.
3. infra: B1 role + B4 wiring; deploy with Malcolm still running (parallel bring-up).
4. Validate `/mcp` (Claude/chives) and `/v1` (a reminders call) against storage.
5. B3 reminders.db migration during a brief Malcolm stop.
6. B6 flip DNS to storage; verify consumers.
7. B5 decommission Malcolm.

## Open items to confirm during implementation

- Exact on-host vault path produced by `system-obsidian-headless` on Ubuntu (for the
  bind mount).
- Whether chives should reach gateway internally (`http://gateway:4000`) or via Traefik.
- Whether to keep or delete the `system-mcp-gateway` role after decommission.
