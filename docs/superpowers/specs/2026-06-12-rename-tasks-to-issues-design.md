# Rename "tasks" to "issues" — design spec

**Date:** 2026-06-12
**Status:** Done

## Motivation

"Tasks" is also used by Claude Code's internal task-tracking system (`TaskCreate`, `TaskUpdate`, etc.), which causes confusion when working in Gateway. Using "issues" for Vikunja project items removes this ambiguity. Apple Reminders (accessible via `gw reminders`) covers personal to-dos, so "issues" is the right term for project-based work items tracked in Vikunja.

## Scope

Full rename: CLI command name, MCP tool names, parameter names, internal Python identifiers, fmt helpers, tests, and the skill doc.

## Files changed

### `gateway/tools/vikunja.py` — MCP tool layer

- `_task_summary` → `_issue_summary`
- All 14 registered tool function names:

| Old | New |
|---|---|
| `list_tasks` | `list_issues` |
| `get_task` | `get_issue` |
| `create_task` | `create_issue` |
| `update_task` | `update_issue` |
| `delete_task` | `delete_issue` |
| `add_task_label` | `add_issue_label` |
| `remove_task_label` | `remove_issue_label` |
| `list_task_comments` | `list_issue_comments` |
| `add_task_comment` | `add_issue_comment` |
| `list_task_relations` | `list_issue_relations` |
| `add_task_relation` | `add_issue_relation` |
| `delete_task_relation` | `delete_issue_relation` |
| `list_task_reminders` | `list_issue_reminders` |
| `set_task_reminders` | `set_issue_reminders` |

- Parameter `task_id: int` → `issue_id: int` in all signatures
- Internal variable `task_id` → `issue_id` in function bodies
- Docstring wording: "task"/"Vikunja task" → "issue"/"Vikunja issue"

### `gateway/cli/commands/vikunja.py` — CLI command definitions

- Group docstring: `"Tasks (Vikunja)."` → `"Issues (Vikunja)."`
- All `client.call_tool(…, "<old_name>", …)` calls updated to use new MCP tool names
- Click argument `"task-id"` → `"issue-id"` (help output shows `ISSUE-ID`)
- Python variable `task_id` → `issue_id` in command function bodies
- Help strings updated: "a task" → "an issue", etc.
- `fmt.tasks(data)` → `fmt.issues(data)`, `fmt.task_detail(data)` → `fmt.issue_detail(data)`

### `gateway/cli/__init__.py`

```python
main.add_command(vikunja.tasks_group, "tasks")
# → 
main.add_command(vikunja.tasks_group, "issues")
```

(The Python group object `tasks_group` can keep its name — it's internal.)

### `gateway/cli/fmt.py`

- `tasks(data)` → `issues(data)`
- `task_detail(t)` → `issue_detail(t)`
- `"No tasks."` → `"No issues."`

### `tests/cli/test_vikunja.py`

- CLI invocations: `["tasks", "list"]` → `["issues", "list"]`, etc.
- Mock targets: `"list_tasks"` → `"list_issues"`, etc.

### `skills/gateway-cli/SKILL.md`

- Section header `### \`gw tasks\`` → `### \`gw issues\``
- All `gw tasks` → `gw issues`
- `TASK_ID` → `ISSUE_ID` in usage examples
- Description line updated: "tasks" → "issues"

## What does NOT change

- The Python group object name `tasks_group` in `vikunja.py` CLI (internal, not user-facing)
- The `projects_group` and project-related tooling (no rename needed)
- Vikunja API URLs (`/tasks/`, `/projects/{id}/tasks`) — these are upstream API paths, not gateway-controlled names
- The Vikunja integration file names (`vikunja.py`) — renaming files is unnecessary churn
