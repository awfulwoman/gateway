# Containerize Gateway and deploy it to the storage host

## Context

Full design rationale lives in the companion spec:
`docs/superpowers/specs/2026-07-19-docker-deployment-design.md`. In short: Gateway moves
off its macOS launchd deployment on Malcolm and runs as a Docker container on
`server-64gb-storage`, deployed the same `composition-*` way as `memorybank`/`chives`.
Storage becomes the sole host; the macOS-only Contacts tool is dropped.

Scope: two repos — `gateway` (image + code changes) and `infra` (deploy role + host
wiring).

## Changes

### Part A — `gateway` repo

#### 1. Gate the Contacts tool to macOS

- `pyproject.toml` — add a platform marker so `uv sync` doesn't try to install a
  macOS-only wheel on Linux:
  ```toml
  "pyobjc-framework-Contacts>=10 ; sys_platform == 'darwin'",
  ```
  Re-run `uv lock` and commit the updated `uv.lock` (it records the marker).
- `gateway/main.py` — drop the top-level `contacts` import, guard registration:
  ```python
  import sys
  ...
  if sys.platform == "darwin":
      from gateway.tools import contacts
      contacts.register(mcp)
  ```
  Result: the container starts with 38 tools (Contacts' 3 absent); macOS behavior is
  unchanged.

#### 2. `Dockerfile`

Modeled on `chives/Dockerfile` (uv base image, two-stage sync for layer caching):

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

#### 3. `.dockerignore`

Model on chives: exclude `.venv/`, `.git`, `tests/`, `.pytest_cache/`, `logs/`, `*.db`,
`.env`, `__pycache__/`, `docs/`, `scripts/`.

#### 4. CI — `.github/workflows/docker.yml`

Copied from `chives/.github/workflows/docker.yml`: builds on push to `main`, pushes
`ghcr.io/awfulwoman/gateway:latest` + `:<sha>`. Repo name resolves automatically via
`github.repository`, no edits needed.

#### 5. `README.md`

Add a "Running in Docker" section (build/run commands, volumes to mount, link to the
spec) and mark the Contacts tool group "(macOS only)" in the tools table.

### Part B — `infra` repo

#### 1. New role `roles/composition-gateway/`

Modeled on `composition-chives` (closest analog — Python, config + state volumes,
Traefik, healthcheck):

- `meta/main.yaml` → depends on `composition-common`.
- `defaults/main.yaml` → all vars that used to live in `system-mcp-gateway/defaults`
  (IMAP, GCal token, Karakeep, OwnTracks, reminders tokens, server auth tokens), reusing
  the same vault vars — no new secrets.
- `templates/environment_vars.j2` → same `GATEWAY_*` keys as the old
  `system-mcp-gateway/templates/env.j2`, but container paths:
  `GATEWAY_SERVER__HOST=0.0.0.0`, `GATEWAY_OBSIDIAN__VAULT_PATH=/vault`,
  `GATEWAY_REMINDERS__DB_PATH=/data/reminders.db`.
- `templates/docker-compose.yaml.j2` → one service, Traefik labels for
  `gateway.{{ domainname_infra }}`, healthcheck per this repo's `docker-healthcheck`
  rule (`bash -c 'echo > /dev/tcp/localhost/4000'`), bind mounts for the DB dir and the
  Obsidian vault.
- `tasks/main.yaml` → assert the vault path var is set, template the compose file +
  `.environment_vars`, create the DB dir, register the `gateway` subdomain via
  `network-register-subdomain`, `docker_compose_v2` with `pull: always`, notify
  `Restart Traefik`.
- `README.md` → documents both HTTP surfaces, the required vault-path var, and that
  Contacts is unavailable in this container.

#### 2. Obsidian vault sync on storage —
   `inventory/host_vars/server-64gb-storage/core.yaml`

- Added a `system_obsidian_headless_vaults` entry for `Charlie`, synced to
  `{{ ansible_facts['user_dir'] }}/obsidian-vaults/Charlie`.
- Added `composition_gateway_obsidian_vault_path` pointing at that same path.
- Added `gateway.{{ domainname_infra }}` to the host's `cnames` list (drives local DNS
  via `infra-named` and Uptime Kuma monitor registration).

#### 3. Wire the storage playbook —
   `playbooks/hosts/server-64gb-storage/core.yaml`

- Added `system-nvm` and `system-obsidian-headless` roles (prerequisites for the vault
  sync).
- Added `composition-gateway`.
- Fixed the `holly` chives instance's gateway MCP entry: it pointed at
  `https://gateway.{{ domainname_infra }}/mcp # on Malcolm`, which had **no DNS record**
  (Malcolm's launchd deployment never called `network-register-subdomain`) and was
  **missing its `auth_key`** — both pre-existing bugs, so this call was already dead.
  Repointed it to the internal Docker network address with the auth key it needed:
  ```yaml
  - url: "http://gateway:4000/mcp" # on same host
    auth_key: "{{ vault_gateway_mcp_token }}"
  ```

#### 4. Decommission Malcolm

- `playbooks/hosts/apple-macmini-m4-16gb-malcolm/core.yaml` — removed the
  `system-mcp-gateway` role entry.
- `inventory/host_vars/apple-macmini-m4-16gb-malcolm/core.yaml` — removed the `Charlie`
  vault entry from `system_obsidian_headless_vaults` (kept `AgentMemory`, which is
  unrelated to Gateway) and removed the `MCP GATEWAY` var section (also cleaned up a
  stray duplicate `HOMEBREW` header left over from an earlier edit in the same spot).
- Deleted `roles/system-mcp-gateway/` entirely — confirmed unreferenced by any other
  host/playbook before removal, and confirmed explicitly with the user before finalizing
  (destructive, though trivially reversible pre-commit via git).

## Tests

- `uv run pytest` — 245 passed (Contacts gating doesn't touch any test path; the CLI's
  `contacts` command module is an HTTP client, not a `pyobjc` consumer).
- `docker build` on the new Dockerfile — verified zero `pyobjc`/`Contacts` install
  attempts in the build log.
- `docker run` the built image — server boots, responds on `/mcp` (406 on a bare GET is
  expected MCP protocol behavior, not a crash), no Contacts-related error.
- `ansible-lint roles/composition-gateway` — clean (0 failures/warnings).
- Rendered both `composition-gateway` templates via Jinja2 directly with sample vars,
  then ran `docker compose config` against the rendered compose file — valid.
- `ansible-lint` across both edited playbooks — only pre-existing warnings in unrelated
  dependency roles (`hardware-apple`, `system-nvm`, `virtual-qemu-host`, etc.), nothing
  in the files this change touches.

## Verification / rollout (operational, not code)

1. Gateway repo merged to `main` → CI publishes `ghcr.io/awfulwoman/gateway:latest`.
2. Manual one-time: `ob login` on the storage host (MFA, not automatable) before running
   `system-obsidian-headless` there.
3. Run the storage playbook (`composition-gateway` + `system-obsidian-headless` tags);
   validate `/mcp` (via `holly`/Claude Code) and `/v1` (a reminders call) against
   storage while Malcolm's deployment is still live.
4. Stop Malcolm's gateway, `scp` its `reminders.db` to
   `{{ composition_config }}/db/reminders.db` on storage, confirm the storage container
   picks it up as the canonical DB.
5. Confirm `gateway.{{ domainname_infra }}` resolves to storage (the new
   `network-register-subdomain` call in `composition-gateway`, plus the `cnames` entry
   for local DNS/monitoring).
6. Run the Malcolm playbook to apply the `system-mcp-gateway` removal (unloads the
   launchd service).

## Follow-up (not code)

- `vault_gateway_gcal_token_json` is referenced by `composition-gateway`'s defaults but
  never defined in any vault file (only split client id/secret vars exist) — a
  pre-existing gap predating this change, left unresolved since fixing Google Calendar
  OAuth wiring is out of scope here.
- Update `.claude/rules/deploy.md` (done) to reflect the new deploy path: push to `main`,
  then run `composition-gateway` on `server-64gb-storage` instead of `system-mcp-gateway`
  on Malcolm.
