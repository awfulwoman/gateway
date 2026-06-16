# Obsidian Issues — Design Spec

## Overview

Replace Vikunja as the issue-tracking backend with Obsidian. Issues become markdown files in the vault, queryable via Obsidian Bases and manageable via the gateway CLI and MCP tools.

## Architecture

Two new modules replace Vikunja entirely:

- `gateway/tools/issues.py` — MCP tools; reads `ObsidianConfig.vault_path` directly
- `gateway/cli/commands/issues.py` — CLI commands; reuses the `gw issues` group name

Retired:

- `gateway/tools/vikunja.py`
- `gateway/cli/commands/vikunja.py`

`gateway/main.py` is updated to register issues tools and drop Vikunja registration.

The `gw projects` CLI group is retired; project is a frontmatter field on issues, no separate concept needed.

## Storage

Issues live at `<vault>/Projects/_issues/`. The underscore prefix keeps the folder sorted above project directories in Obsidian's file explorer.

`<vault>/Projects/<ProjectName>/` folders exist independently for project files (ideas, images, notes) and are not managed by gateway.

### Filename format

```
0042-fix-login-bug.md
```

- Four-digit zero-padded integer ID (`%04d`)
- Hyphen separator
- Slug generated from title at creation time (lowercase, spaces → hyphens, non-alphanumeric stripped)
- CLI references issues by numeric ID only; slug is for manual vault navigation

### Next ID

At create time, scan `_issues/` and read the `id` frontmatter field from all files. Next ID = max existing ID + 1 (or 1 if empty).

## Data Model

```markdown
---
id: 42
title: Fix login bug
project: MyProject
status: open
priority: 0
due: 2026-07-01
labels:
  - bug
reminders:
  - 2026-06-30T09:00:00Z
related:
  - 17
---

Description prose here.

## Checklist

- [ ] First step
- [x] Done step

## Comments

### 2026-06-16T10:30

First comment.
```

### Field reference

| Field | Type | Values |
|-------|------|--------|
| `id` | integer | auto-assigned, immutable |
| `title` | string | canonical title; filename slug is derived at creation only |
| `project` | string | matches a `Projects/<name>/` directory by convention |
| `status` | string | `open` \| `in-progress` \| `done` |
| `priority` | integer | 0 (none) – 5 (critical) |
| `due` | ISO date | `YYYY-MM-DD` |
| `labels` | list of strings | free-form |
| `reminders` | list of ISO datetimes | `YYYY-MM-DDTHH:MM:SSZ` |
| `related` | list of integers | IDs of related issues (flat, untyped) |

Body sections:

- **Description** — prose between frontmatter and `## Checklist`
- **Checklist** — standard markdown task items (`- [ ]` / `- [x]`), rendered natively by Obsidian
- **Comments** — each comment is a `### <ISO timestamp>` heading followed by prose; appended in order

## MCP Tools

```
list_issues(project, status, priority, label)
    Scan _issues/, parse frontmatter, return filtered list of issue summaries.

get_issue(issue_id)
    Find file whose numeric prefix matches issue_id. Return frontmatter + full body.

create_issue(title, project, description, due, priority, labels, reminders, related, checklist_items)
    Determine next ID, generate slug from title, write file from template.

update_issue(issue_id, title, status, project, description, due, priority, labels, reminders, related)
    Rewrite frontmatter fields; replace description prose (between frontmatter and ## Checklist).

delete_issue(issue_id)
    Delete the file whose numeric prefix matches issue_id.

add_issue_comment(issue_id, comment)
    Append ### <current ISO timestamp>\n\n<comment> to the ## Comments section.

add_checklist_item(issue_id, item)
    Append - [ ] <item> to the ## Checklist section.

toggle_checklist_item(issue_id, item_text)
    Find checklist line matching item_text, flip [ ] ↔ [x].
```

## CLI Commands

```
gw issues list [--project X] [--status open] [--priority N] [--label X]
gw issues get 42
gw issues create "title" [--project X] [--description X] [--due X] [--priority N] [--label X]
gw issues update 42 [--title X] [--status X] [--project X] [--due X] [--priority N]
gw issues delete 42
gw issues comment 42 "text"
gw issues check 42 "item text"     — add a checklist item
gw issues toggle 42 "item text"    — flip done/undone on a checklist item
```

## Obsidian Templates

### `_templates/Issue.md`

Scaffolds a new issue note manually within Obsidian:

```markdown
---
id: 
title: 
project: 
status: open
priority: 0
due: 
labels: []
reminders: []
related: []
---



## Checklist

- [ ] 

## Comments
```

### `_templates/Bases/Issues.md`

A Bases view over `Projects/_issues/` displaying all issues as a table. Default columns: id, title, project, status, priority, due, labels. Filterable and sortable by any frontmatter field.
