# Gateway Server + CLI tools

MCP server providing Claude Code access to personal services: email, Google Calendar, macOS Reminders/Contacts, an Obsidian vault, and Karakeep bookmarks.

## Tools (41 total)

| Group | Tools |
|---|---|
| **Calendar** | `list_calendars`, `list_calendar_events`, `search_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` |
| **Reminders** | `list_reminder_lists`, `list_reminders`, `create_reminder`, `complete_reminder`, `delete_reminder`, `search_reminders` |
| **Contacts** | `lookup_contact`, `search_contacts`, `list_contacts` |
| **Email** | `list_folders`, `list_emails`, `fetch_unread_emails`, `search_emails`, `fetch_email_body`, `mark_email_read` |
| **Obsidian** | `list_notes`, `read_note`, `search_notes`, `create_note`, `update_note`, `append_to_note`, `move_note`, `delete_note` |
| **Karakeep** | `search_bookmarks`, `get_bookmark`, `get_bookmark_content`, `create_bookmark`, `update_bookmark`, `attach_tags`, `detach_tags`, `list_tags`, `get_lists`, `create_list`, `add_to_list`, `remove_from_list` |

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

## Google Calendar setup

Calendar events are read/written via the Google Calendar API, authenticated as you
(OAuth), not a service account — so events you create keep you as organizer and every
calendar your account can see is visible without sharing it separately.

One-time bootstrap, on a machine with a browser:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and
   enable the **Google Calendar API**.
2. Configure the OAuth consent screen (External, add yourself as a test user), then
   **publish** it — apps left in "Testing" mode get refresh tokens that expire after 7
   days.
3. Create an OAuth client ID of type **Desktop app** and copy its **client ID** and
   **client secret** from the credentials page (no need to download the JSON file).
4. Run the bootstrap script, which opens a browser for consent and prints the
   resulting credentials as JSON:
   ```bash
   uv run python -m gateway.gcal_auth <client-id> <client-secret>
   ```
5. Set `GATEWAY_GCAL__TOKEN_JSON` to that JSON output (see Configuration below).

The access token is refreshed automatically at runtime from the embedded refresh
token; re-run the bootstrap only if it's revoked or expires.

## Install as a launchd service (Mac)

```bash
./scripts/install_service.sh
```

This writes a launchd plist, grants TCC permission for Contacts, and starts the service. It will restart automatically on reboot.

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
| `GATEWAY_GCAL__TOKEN_JSON` | Google Calendar OAuth credentials, as JSON (see Google Calendar setup above) |
| `GATEWAY_KARAKEEP__BASE_URL` | Karakeep instance URL |
| `GATEWAY_KARAKEEP__API_KEY` | Karakeep API key |
| `GATEWAY_SERVER__HOST` | SSE server bind address (default 127.0.0.1) |
| `GATEWAY_SERVER__PORT` | SSE server port (default 4000) |
