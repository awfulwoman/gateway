# `gw` CLI Design

**Date:** 2026-06-07
**Status:** Done

## Summary

Add a `gw` CLI command that exposes all 41 gateway MCP tools as shell commands. The existing `gateway` server entry point is unchanged. `gw` is a thin HTTP client that calls the running gateway server.

## Goals

- Every MCP tool accessible from the shell
- `gh`-style `gw <resource> <action> [args]` command structure
- Human-readable output by default; `--json` for raw JSON
- No new runtime dependencies (`httpx` already in project)
- Skill document in the project repo so agents know how to use `gw`

## Architecture

### New files

```
gateway/cli/
  __init__.py        ← Click root group; global --server / --json flags
  client.py          ← call_tool(name, **kwargs) → dict via httpx JSON-RPC
  fmt.py             ← human-readable formatters (one function per tool group)
  commands/
    __init__.py
    calendar.py
    reminders.py
    contacts.py
    email.py
    obsidian.py
    karakeep.py
    owntracks.py
    vikunja.py

skills/
  gateway-cli/
    SKILL.md         ← agent skill doc; copy to ~/.claude/skills/gateway-cli/SKILL.md to activate
```

`pyproject.toml` gains a second entry point:
```toml
gw = "gateway.cli:main"
```

### HTTP client (`client.py`)

Posts MCP JSON-RPC to `/mcp`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "<tool_name>", "arguments": { ... } }
}
```

Parses `result.content[0].text` as JSON. Raises `GatewayError` on connection failure, non-2xx response, or `error` key in JSON-RPC response.

Server URL: `GATEWAY_URL` env var → `--server` flag → default `http://127.0.0.1:4000/mcp`.

### Formatters (`fmt.py`)

`format_output(tool_name, data, as_json)` dispatches to per-group formatter. With `--json`, bypasses all formatting and prints `json.dumps(data, indent=2)`. Human formatters use stdlib string formatting only (no tabulate/rich).

## Command Reference

Global flags (on the root `gw` command, available to all subcommands):
- `--server URL` — override server URL
- `--json` — output raw JSON instead of formatted text

### Calendar

```
gw calendar list-events <period>
    period: today | tomorrow | week | month | YYYY-MM-DD:YYYY-MM-DD

gw calendar search <query>

gw calendar create <title> <start> <end>
    --location TEXT
    --notes TEXT
    --calendar TEXT

gw calendar update <event-id>
    --title TEXT
    --start ISO
    --end ISO
    --location TEXT
    --notes TEXT

gw calendar delete <event-id>
```

### Reminders

```
gw reminders list
    --list TEXT   filter by reminder list name

gw reminders search <query>

gw reminders create <title>
    --list TEXT
    --due ISO
    --notes TEXT

gw reminders complete <reminder-id>

gw reminders delete <reminder-id>
```

### Contacts

```
gw contacts list
gw contacts lookup <name>
gw contacts search <query>
```

### Email

```
gw email folders
gw email list [--folder TEXT] [--limit INT]
gw email unread
gw email search <query>
gw email read <message-id>
gw email mark-read <message-id>
```

### Notes (Obsidian)

```
gw notes list [--folder PATH]
gw notes read <path>
gw notes search <query>
gw notes create <title> <content>
gw notes update <path> <content>
gw notes append <path> <content>
gw notes move <path> <dest>
gw notes delete <path>
```

### Bookmarks (Karakeep)

```
gw bookmarks search <query>
gw bookmarks get <id>
gw bookmarks create <url>
gw bookmarks tags
gw bookmarks lists
```

### Tasks (Vikunja)

```
gw tasks list [--project TEXT] [--filter EXPR]
gw tasks get <id>
gw tasks create <title>
    --project INT
    --due ISO
    --priority INT

gw tasks update <id>
    --title TEXT
    --done
    --due ISO
    --priority INT

gw tasks delete <id>
gw tasks comments <id>
gw tasks comment <id> <text>
gw tasks relations <id>
gw tasks reminders <id>
```

### Location (OwnTracks)

```
gw location current
gw location history
gw location devices
```

## Skill document

`skills/gateway-cli/SKILL.md` is the authoritative reference for agents. It covers:
- When to use `gw` (shell scripting, human-readable inspection, piping to `jq`)
- When to prefer MCP tools directly (structured tool calls from within Claude)
- Full command reference with examples

To activate for an agent: copy to `~/.claude/skills/gateway-cli/SKILL.md` and add to Chezmoi.

## Error handling

- Connection refused → clear message: `gateway server is not running (tried <url>)`
- Tool error → print error message from JSON-RPC response, exit 1
- Missing required arg → Click handles automatically with usage hint

## Testing

Existing `tests/` suite is integration-only. CLI commands are thin wrappers; no new unit tests required. Manual verification: run `uv run gw calendar list-events today` against the live server.
