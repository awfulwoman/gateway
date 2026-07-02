---
name: gateway-cli
description: Use gw CLI commands to interact with gateway services (calendar, email, notes, issues, bookmarks, location, contacts, reminders) from the shell. Use instead of MCP tools when scripting, piping output, or wanting human-readable inspection.
metadata:
  type: reference
---

# gateway-cli skill

## When to use `gw` vs MCP tools

| Scenario | Prefer |
|---|---|
| Shell scripting, piping to `jq`, `grep`, etc. | `gw` CLI |
| Human-readable inspection of data | `gw` CLI |
| Structured tool calls from within Claude | MCP tools |
| Composing multiple operations in one turn | MCP tools |

## Setup

The gateway server must be running before any `gw` command. By default `gw` connects to `http://127.0.0.1:4000/mcp`. Override with the `GATEWAY_URL` environment variable or the `--server` flag.

```bash
# override server for one command
gw --server http://other-host:4000/mcp calendar list-calendars

# or export for the session
export GATEWAY_URL=http://other-host:4000/mcp
```

## Global flags

| Flag | Description |
|---|---|
| `--server URL` | Override the gateway server URL |
| `--help` | Show help for any command |

`--json` is a per-subcommand flag (not global). Place it after the full subcommand:

```bash
gw calendar list-events today --json
gw issues list --project 3 --json
```

---

## Command reference

### `gw calendar`

```bash
gw calendar list-calendars
gw calendar list-events PERIOD          # today | tomorrow | week | month | YYYY-MM-DD:YYYY-MM-DD
gw calendar search QUERY [--days-ahead 90]
gw calendar create TITLE START END [--location TEXT] [--notes TEXT] [--calendar TEXT]
gw calendar update EVENT_ID [--title TEXT] [--start TEXT] [--end TEXT] [--location TEXT] [--notes TEXT]
gw calendar delete EVENT_ID
```

START/END are ISO 8601, e.g. `2026-06-08T14:00:00`.

```bash
# examples
gw calendar list-events week
gw calendar list-events 2026-06-01:2026-06-30
gw calendar create "Team standup" 2026-06-09T09:00:00 2026-06-09T09:30:00 --calendar Work
gw calendar search "dentist"
gw calendar list-events today --json | jq '.[].title'
```

---

### `gw reminders`

```bash
gw reminders lists
gw reminders list [--list NAME] [--completed]
gw reminders search QUERY
gw reminders create TITLE [--list NAME] [--due TEXT] [--notes TEXT] [--priority INT] \
    [--location TEXT] [--arrive-or-leave arrive|leave]
gw reminders complete TITLE          # substring match
gw reminders delete TITLE            # substring match
```

```bash
# examples
gw reminders lists
gw reminders list --list Shopping
gw reminders list --completed
gw reminders create "Buy milk" --list Shopping --due "tomorrow 9am"
gw reminders create "Leave for airport" --location "Home" --arrive-or-leave leave
gw reminders complete "Buy milk"
gw reminders search "airport" --json
```

---

### `gw contacts`

```bash
gw contacts list [--limit 50]
gw contacts lookup NAME
gw contacts search QUERY
```

```bash
# examples
gw contacts list --limit 10
gw contacts lookup "Alice"
gw contacts search "alice@example.com"
gw contacts list --json | jq '.[].name'
```

---

### `gw email`

```bash
gw email folders
gw email list [--folder INBOX] [--limit 20]
gw email unread
gw email search QUERY [--in all|subject|from|body] [--folder INBOX] [--limit 20]
gw email read MESSAGE_ID
gw email mark-read MESSAGE_ID
```

```bash
# examples
gw email folders
gw email list --folder Sent --limit 5
gw email unread --json | jq '.[].subject'
gw email search "invoice" --in subject
gw email search "Charlie" --in from --folder Sent
gw email read "<msg-id@example.com>"
```

---

### `gw notes`

```bash
gw notes list [--folder PATH]
gw notes read PATH
gw notes search QUERY [--folder PATH]
gw notes create PATH CONTENT
gw notes update PATH CONTENT          # overwrites
gw notes append PATH CONTENT          # creates if absent
gw notes move PATH DEST
gw notes delete PATH
```

PATH is relative to the vault root.

```bash
# examples
gw notes list --folder Projects
gw notes read "Projects/gateway.md"
gw notes search "vikunja"
gw notes create "Scratch/temp.md" "# Temp note"
gw notes append "Journal/2026-06-07.md" "\n## Evening\nGood day."
gw notes move "Scratch/temp.md" "Archive/temp.md"
gw notes delete "Scratch/old.md"
```

---

### `gw bookmarks`

```bash
gw bookmarks search QUERY [--limit 10] [--cursor TEXT]
gw bookmarks get BOOKMARK_ID
gw bookmarks content BOOKMARK_ID
gw bookmarks create URL_OR_TEXT [--type link|text] [--title TEXT]
gw bookmarks update BOOKMARK_ID [--title TEXT] [--note TEXT] [--archived true|false] [--favourited true|false]
gw bookmarks tag BOOKMARK_ID TAGS          # TAGS is comma-separated
gw bookmarks untag BOOKMARK_ID TAGS
gw bookmarks tags
gw bookmarks lists
gw bookmarks create-list NAME ICON [--parent TEXT]    # ICON should be an emoji
gw bookmarks add-to-list LIST_ID BOOKMARK_ID
gw bookmarks remove-from-list LIST_ID BOOKMARK_ID
```

Search qualifiers: `is:fav`, `is:archived`, `#tag`, `url:value`.

```bash
# examples
gw bookmarks search "kubernetes"
gw bookmarks search "is:fav #devops"
gw bookmarks search "#python" --limit 20
gw bookmarks create "https://example.com" --title "Example site"
gw bookmarks create "Some interesting text" --type text
gw bookmarks tag abc123 "python,devops"
gw bookmarks tags
gw bookmarks lists
gw bookmarks search "rust" --json | jq '.[].url'
```

---

### `gw issues`

Issues are stored as Obsidian markdown files under `Projects/{topic}/{project}/_issues/`.
`--project` takes a vault-relative path, e.g. `Software/Podderton`.

```bash
gw issues list [--project PATH] [--status open|in-progress|done] [--priority INT] [--label TEXT]
gw issues get ISSUE_ID
gw issues create TITLE --project PATH [--description TEXT] [--due YYYY-MM-DD] \
    [--priority INT] [--label TEXT]...
gw issues update ISSUE_ID [--title TEXT] [--status open|in-progress|done] \
    [--project PATH] [--description TEXT] [--due YYYY-MM-DD] [--priority INT]
gw issues delete ISSUE_ID
gw issues comment ISSUE_ID COMMENT
gw issues check ISSUE_ID ITEM          # add a checklist item
gw issues toggle ISSUE_ID ITEM_TEXT    # flip done/undone by exact item text
```

```bash
# examples
gw issues list
gw issues list --project Software/Podderton
gw issues list --status open --priority 2
gw issues list --label bug --json | jq '.[].title'
gw issues get 42
gw issues create "Fix login bug" --project Software/Podderton --due 2026-07-10 --priority 2 --label bug
gw issues update 42 --status in-progress
gw issues update 42 --status done
gw issues comment 42 "Investigated — root cause is JWT expiry"
gw issues check 42 "Write regression test"
gw issues toggle 42 "Write regression test"
```

---

### `gw location`

```bash
gw location current
gw location history [--from TEXT] [--to TEXT] [--user TEXT] [--device TEXT] [--limit 100]
gw location devices
```

```bash
# examples
gw location current
gw location devices
gw location history --from "2026-06-01" --to "2026-06-07"
gw location history --limit 10 --json | jq '.[].lat'
```

---

## Common patterns

```bash
# List today's events as plain text
gw calendar list-events today

# List open issues for a project
gw issues list --project Software/Podderton --status open --json | jq '.[].title'

# Search notes and show path + snippet
gw notes search "meeting notes" --json | jq '.[] | {path, snippet}'

# Check unread emails, show subjects
gw email unread --json | jq '.[].subject'

# Find favourite bookmarks tagged devops
gw bookmarks search "is:fav #devops" --json | jq '.[].url'

# Create an issue with checklist items
gw issues create "Deploy v2" --project Software/Podderton --due 2026-07-15
gw issues check 1 "Update changelog"
gw issues check 1 "Tag release"
```

---

## Deployment

To make this skill available to your agent, copy it to the user skills directory and add it to Chezmoi:

```bash
mkdir -p ~/.claude/skills/gateway-cli
cp /path/to/gateway/skills/gateway-cli/SKILL.md ~/.claude/skills/gateway-cli/SKILL.md
chezmoi add ~/.claude/skills/gateway-cli/SKILL.md
```
