# Gateway Server + CLI tools

MCP server providing Claude Code access to personal services: email, Calendar (backed by real Apple Calendar via [apple-calendar-server](https://github.com/awfulwoman/apple-calendar-server)), Contacts (backed by real macOS Contacts via [apple-contacts-server](https://github.com/awfulwoman/apple-contacts-server)), Reminders (backed by real Apple Reminders via [apple-reminders-server](https://github.com/awfulwoman/apple-reminders-server)), an Obsidian vault, Karakeep bookmarks, OwnTracks location, and issues (GitHub issues in the `awfulwoman/meta` repo).

## Tools (55 total)

| Group | Tools |
|---|---|
| **Calendar** | `list_calendars`, `list_calendar_events`, `search_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` |
| **Reminders** | `list_reminder_lists`, `list_reminders`, `create_reminder`, `complete_reminder`, `delete_reminder`, `search_reminders` |
| **Contacts** | `lookup_contact`, `search_contacts`, `list_contacts`, `create_contact`, `update_contact`, `delete_contact` |
| **Email** | `list_folders`, `list_emails`, `fetch_unread_emails`, `search_emails`, `fetch_email_body`, `mark_email_read` |
| **Obsidian** | `list_notes`, `read_note`, `search_notes`, `create_note`, `update_note`, `append_to_note`, `move_note`, `delete_note` |
| **Karakeep** | `search_bookmarks`, `get_bookmark`, `get_bookmark_content`, `create_bookmark`, `update_bookmark`, `attach_tags`, `detach_tags`, `list_tags`, `get_lists`, `create_list`, `add_to_list`, `remove_from_list` |
| **OwnTracks** | `get_current_location`, `get_location_history`, `list_tracked_devices` |
| **Issues** (GitHub `awfulwoman/meta`) | `list_issues`, `get_issue`, `create_issue`, `update_issue`, `delete_issue`, `add_issue_comment`, `add_checklist_item`, `toggle_checklist_item` |

## Setup

```bash
# Install dependencies
uv sync

# Copy and fill in credentials
cp .env.example .env
$EDITOR .env
```

## Running

**SSE mode** (persistent HTTP server, default):
```bash
uv run gateway
# Listening at http://127.0.0.1:4000/sse
```

**stdio mode** (spawned on demand by Claude Code):
```bash
uv run gateway --transport stdio
```

## Running in Docker

```bash
docker build -t gateway .
docker run -d --name gateway -p 4000:4000 --env-file .env gateway
```

Contacts, Reminders, and Calendar are backed by apple-contacts-server /
apple-reminders-server / apple-calendar-server, reached over HTTP via
`GATEWAY_CONTACTS_SERVER__*` / `GATEWAY_REMINDERS_SERVER__*` /
`GATEWAY_CALENDAR_SERVER__*` — all three run natively on Malcolm (the always-on Mac,
for Contacts/EventKit access), not in this container. All three work the same in the
container as on macOS — no platform-specific dependency to exclude here. Mount
`GATEWAY_OBSIDIAN__VAULT_PATH` as a volume so notes persist across container restarts. See
[`docs/superpowers/specs/2026-07-19-docker-deployment-design.md`](docs/superpowers/specs/2026-07-19-docker-deployment-design.md)
for the design and
[`docs/superpowers/plans/2026-07-19-docker-deployment.md`](docs/superpowers/plans/2026-07-19-docker-deployment.md)
for the implementation plan (container image, Ansible role, host migration).

## apple-calendar-server setup (Calendar)

Calendar events are backed by real Apple Calendar (via `EventKit`), fronted by a
small authorised REST API — [apple-calendar-server](https://github.com/awfulwoman/apple-calendar-server) —
running natively on Malcolm, the always-on Mac (EventKit is macOS-only and needs a
logged-in GUI session for the Calendar permission grant, so it can't run in this
container). This replaced Google Calendar as the calendar backend, mirroring the
Reminders migration below: multiple calendars are first-class (see
`list_calendars`), and events created on any Apple device — not just through
Gateway — show up here too.

1. Deploy apple-calendar-server on Malcolm (see its own README, and the infra role
   `system-apple-calendar-server`).
2. Set `GATEWAY_CALENDAR_SERVER__BASE_URL` and `__BEARER_TOKEN` to match.

## apple-contacts-server setup (Contacts)

Contacts are backed by real macOS Contacts (via the `Contacts` framework), fronted by
a small authorised REST API — [apple-contacts-server](https://github.com/awfulwoman/apple-contacts-server) —
running natively on Malcolm, the always-on Mac (the Contacts framework is macOS-only
and needs a logged-in GUI session for the permission grant, so it can't run in this
container). This replaced Radicale as the contacts backend, mirroring the Reminders
migration below: contacts created via Siri, another device, or the Contacts app show
up here too, instead of only ever seeing writes that went through Gateway itself.

1. Deploy apple-contacts-server on Malcolm (see its own README, and the infra role
   `system-apple-contacts-server`).
2. Set `GATEWAY_CONTACTS_SERVER__BASE_URL` and `__BEARER_TOKEN` to match.

Unlike Reminders and Calendar, there's no offline-sync `/v1` API or LWW/tombstone
contract for Contacts — see
[`docs/superpowers/specs/2026-07-19-radicale-contacts-reminders-design.md`](docs/superpowers/specs/2026-07-19-radicale-contacts-reminders-design.md)
for the original Radicale-backed design this backend swap builds on.

## apple-reminders-server setup (Reminders)

Reminders are backed by real Apple Reminders (via `EventKit`), fronted by a small
authorised REST API — [apple-reminders-server](https://github.com/awfulwoman/apple-reminders-server) —
running natively on Malcolm, the always-on Mac (EventKit is macOS-only and needs a
logged-in GUI session for the Reminders permission grant, so it can't run in this
container). This replaced Radicale as the reminders backend so that reminders created
via Siri, the Reminders widget, or any Apple device show up through Gateway too,
instead of only ever seeing writes that went through Gateway itself.

1. Deploy apple-reminders-server on Malcolm (see its own README, and the infra role
   `system-apple-reminders-server`).
2. Set `GATEWAY_REMINDERS_SERVER__BASE_URL` and `__BEARER_TOKEN` to match.

The `/v1/reminders` JSON-HTTP sync API (`gateway/reminders/http.py`) and its own auth
(`GATEWAY_REMINDERS__API_TOKENS`) are unaffected by this — same offline-sync protocol
as before; only the storage backend behind `gateway/reminders/store.py` changed.

## Install as a launchd service (Mac)

```bash
./scripts/install_service.sh
```

This writes a launchd plist and starts the service. It will restart automatically on reboot.

To remove:
```bash
./scripts/uninstall_service.sh
```

## Claude Code integration

After running the service, register it at user scope (available across all projects). Use the CLI rather than editing config files directly — the `claude` CLI manages the internal storage format and may change it between versions.


```bash
claude mcp add --transport http gateway --scope user http://127.0.0.1:4000/mcp
```

Or for stdio mode (Claude Code spawns the process on demand):

```bash
claude mcp add --scope user gateway -- uv --project /path/to/gateway run gateway --transport stdio
```

## CLI (`gw`)

A command-line client for the same tools, useful for scripting or quick lookups
without going through Claude.

```bash
gw calendar list-events today
gw reminders list --list Shopping
gw bookmarks search "python"
```

Global options:

| Option | Env var | Default | Description |
|---|---|---|---|
| `--server` | `GATEWAY_URL` | `http://127.0.0.1:4000/mcp` | Gateway server URL |
| `--token` | `GATEWAY_TOKEN` | (none) | Bearer token, sent as `Authorization: Bearer <token>` — only needed if the server has auth enabled |

Command groups: `calendar`, `reminders`, `contacts`, `email`, `notes`, `bookmarks`,
`location`, `issues`. Run `gw --help` or `gw <group> --help` for the full list of
subcommands.

## Configuration

All config via environment variables (or `.env` file):

| Variable | Description |
|---|---|
| `GATEWAY_IMAP__HOST` | IMAP server hostname |
| `GATEWAY_IMAP__PORT` | IMAP port (default 993) |
| `GATEWAY_IMAP__USERNAME` | IMAP username |
| `GATEWAY_IMAP__PASSWORD` | IMAP password |
| `GATEWAY_OBSIDIAN__VAULT_PATH` | Absolute path to Obsidian vault |
| `GATEWAY_CALENDAR_SERVER__BASE_URL` | apple-calendar-server base URL (see apple-calendar-server setup above) |
| `GATEWAY_CALENDAR_SERVER__BEARER_TOKEN` | apple-calendar-server bearer token |
| `GATEWAY_KARAKEEP__BASE_URL` | Karakeep instance URL |
| `GATEWAY_KARAKEEP__API_KEY` | Karakeep API key |
| `GATEWAY_GITHUB__REPO` | Repo holding issues (default `awfulwoman/meta`), reached via the GitHub REST API. |
| `GATEWAY_GITHUB__TOKEN` | GitHub PAT with `Issues: Read and write` on that repo. |
| `GATEWAY_SERVER__HOST` | SSE server bind address (default 127.0.0.1) |
| `GATEWAY_SERVER__PORT` | SSE server port (default 4000) |
| `GATEWAY_SERVER__AUTH_TOKENS` | Comma-separated bearer tokens required on `/mcp`. Each entry is `label:secret` (label names the caller in the usage log); a bare `secret` gets an auto label. Unset = auth disabled (startup warning). |
| `GATEWAY_USAGE_LOG__ENABLED` | Log one JSON line per `/mcp` request (default `true`). |
| `GATEWAY_USAGE_LOG__PATH` | Also append pure JSONL to this rotating file (unset = stdout only). |
| `GATEWAY_USAGE_LOG__MAX_BYTES` / `__BACKUPS` | Rotation size and kept-file count (defaults 10 MiB, 5). |

## Usage logging

Every `/mcp` request emits one structured line via the `gateway.usage` logger —
to stdout prefixed `usage `, and to `GATEWAY_USAGE_LOG__PATH` as pure JSONL when
set. `/v1/*` is not covered (it is slated for removal — see
[issue #1](https://github.com/awfulwoman/gateway/issues/1)).

```json
{"ts":"2026-09-10T19:33:54.796984Z","caller":"laptop","ip":"127.0.0.1",
 "ua":"claude-code/1.2","status":200,"duration_ms":9.4,
 "method":"tools/call","tool":"list_notes","args":{"limit":3},"rpc_id":1}
```

`caller` is the label of the matched `GATEWAY_SERVER__AUTH_TOKENS` entry, or
`null` for an unauthenticated / rejected request. `args` is the full tool
arguments object. A JSON-RPC batch logs one line per sub-call.
