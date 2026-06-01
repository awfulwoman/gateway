# gateway

MCP server providing Claude Code access to personal services: email, macOS Calendar/Reminders/Contacts, an Obsidian vault, and Karakeep bookmarks.

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

## Install as a launchd service (Mac)

```bash
./scripts/install_service.sh
```

This writes a launchd plist, grants TCC permissions for Calendar/Reminders/Contacts, and starts the service. It will restart automatically on reboot.

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

## Configuration

All config via environment variables (or `.env` file):

| Variable | Description |
|---|---|
| `GATEWAY_IMAP__HOST` | IMAP server hostname |
| `GATEWAY_IMAP__PORT` | IMAP port (default 993) |
| `GATEWAY_IMAP__USERNAME` | IMAP username |
| `GATEWAY_IMAP__PASSWORD` | IMAP password |
| `GATEWAY_OBSIDIAN__VAULT_PATH` | Absolute path to Obsidian vault |
| `GATEWAY_KARAKEEP__BASE_URL` | Karakeep instance URL |
| `GATEWAY_KARAKEEP__API_KEY` | Karakeep API key |
| `GATEWAY_SERVER__HOST` | SSE server bind address (default 127.0.0.1) |
| `GATEWAY_SERVER__PORT` | SSE server port (default 4000) |
