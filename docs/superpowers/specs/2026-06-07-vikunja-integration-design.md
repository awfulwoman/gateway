# Vikunja Integration Design

**Date:** 2026-06-07
**Status:** Approved

## Overview

Add a `vikunja.py` tool module to the gateway MCP server, exposing Vikunja task and project management as 18 MCP tools. Use case: read and write tasks, projects, labels, comments, relations, and reminders mid-conversation.

## Config & Auth

Add `VikunjaConfig` to `config.py`:

```python
class VikunjaConfig(BaseModel):
    base_url: str = ""
    api_token: str = ""
```

Add to `Config` as `vikunja: VikunjaConfig = VikunjaConfig()`. Env vars: `GATEWAY_VIKUNJA__BASE_URL` and `GATEWAY_VIKUNJA__API_TOKEN`. Auth is `Authorization: Bearer <api_token>` on every request, generated once in Vikunja's UI settings.

Add entries to `.env.example`:

```
GATEWAY_VIKUNJA__BASE_URL=https://vikunja.example.com
GATEWAY_VIKUNJA__API_TOKEN=your-api-token
```

## Tool Module

Single file: `gateway/tools/vikunja.py`. Follows the existing `init()` / `_client()` / `register()` pattern from `karakeep.py`.

### Projects (3 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_projects` | — | All projects the token can access |
| `get_project` | `project_id` | Single project by ID |
| `create_project` | `title`, `description?`, `parent_project_id?` | New project |

### Tasks (4 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_tasks` | `project_id?`, `filter_by?`, `order_by?`, `page?` | List tasks; `filter_by` accepts Vikunja filter syntax e.g. `done=false` |
| `get_task` | `task_id` | Single task with full detail |
| `create_task` | `project_id`, `title`, `description?`, `due_date?`, `priority?` | New task |
| `update_task` | `task_id`, `title?`, `description?`, `done?`, `due_date?`, `priority?` | Partial update — only non-empty fields sent |
| `delete_task` | `task_id` | Delete a task |

### Labels (3 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_labels` | — | All labels accessible to the token |
| `add_task_label` | `task_id`, `label_id` | Attach label to task |
| `remove_task_label` | `task_id`, `label_id` | Detach label from task |

### Comments (2 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_task_comments` | `task_id` | All comments on a task |
| `add_task_comment` | `task_id`, `comment` | Post a comment |

### Relations (3 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_task_relations` | `task_id` | All relations on a task |
| `add_task_relation` | `task_id`, `other_task_id`, `relation_kind` | Create relation; `relation_kind` values: `subtask`, `parenttask`, `related`, `duplicates`, `duplicated_by`, `blocked_by`, `blocking`, `precedes`, `follows`, `copied_from`, `copied_to` |
| `delete_task_relation` | `task_id`, `relation_id` | Remove a relation |

### Reminders (3 tools)

| Tool | Params | Description |
|------|--------|-------------|
| `list_task_reminders` | `task_id` | All reminders on a task |
| `add_task_reminder` | `task_id`, `reminder_date` | ISO 8601 datetime |
| `delete_task_reminder` | `task_id`, `reminder_id` | Remove a reminder |

## Error Handling

HTTP errors from `httpx` propagate as exceptions; FastMCP surfaces them to the LLM as error responses. No special wrapping. The `_client()` helper asserts config is present before making requests.

## Registration

`main.py`:
- Import `vikunja` alongside existing tool modules
- Call `vikunja.init(config.vikunja)` and `vikunja.register(mcp)` in `create_server()`
