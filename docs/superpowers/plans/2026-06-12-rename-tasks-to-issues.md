# Rename "tasks" to "issues" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename all user-facing "task" terminology to "issue" across the Vikunja MCP tools, CLI commands, formatters, tests, and skill doc — without changing behaviour.

**Architecture:** Pure rename — no behaviour changes. Update tests first (they define the target API surface), then rename implementation to match. Commit once tests pass, then update the skill doc separately.

**Tech Stack:** Python, Click (CLI), FastMCP (MCP tools), pytest

---

## File map

| File | Change |
|---|---|
| `tests/test_vikunja.py` | Rename all `vikunja.*_task*` call sites to `*_issue*` |
| `tests/cli/test_vikunja.py` | Rename `["tasks", ...]` → `["issues", ...]`; rename mock tool targets |
| `gateway/tools/vikunja.py` | Rename 14 tool functions + `_task_summary`; `task_id` → `issue_id`; `other_task_id` → `other_issue_id`; update docstrings |
| `gateway/cli/fmt.py` | `tasks()` → `issues()`; `task_detail()` → `issue_detail()`; "No tasks." → "No issues." |
| `gateway/cli/commands/vikunja.py` | Rename CLI functions; update `call_tool` targets; `task-id` → `issue-id`; update fmt calls; update docstrings |
| `gateway/cli/__init__.py` | `"tasks"` → `"issues"` in `add_command` |
| `skills/gateway-cli/SKILL.md` | `gw tasks` → `gw issues`; `TASK_ID` → `ISSUE_ID` |

---

## Task 1: Update tests to reflect new names (tests will fail)

**Files:**
- Modify: `tests/test_vikunja.py`
- Modify: `tests/cli/test_vikunja.py`

- [ ] **Step 1: Update `tests/test_vikunja.py`**

Replace every call to the old function names. The function-level renames in this file:

| Old call | New call |
|---|---|
| `vikunja.list_tasks(...)` | `vikunja.list_issues(...)` |
| `vikunja.get_task(10)` | `vikunja.get_issue(10)` |
| `vikunja.create_task(...)` | `vikunja.create_issue(...)` |
| `vikunja.update_task(10, ...)` | `vikunja.update_issue(10, ...)` |
| `vikunja.delete_task(10)` | `vikunja.delete_issue(10)` |
| `vikunja.add_task_label(task_id=10, label_id=1)` | `vikunja.add_issue_label(issue_id=10, label_id=1)` |
| `vikunja.remove_task_label(task_id=10, label_id=1)` | `vikunja.remove_issue_label(issue_id=10, label_id=1)` |
| `vikunja.list_task_comments(10)` | `vikunja.list_issue_comments(10)` |
| `vikunja.add_task_comment(10, "...")` | `vikunja.add_issue_comment(10, "...")` |
| `vikunja.list_task_relations(10)` | `vikunja.list_issue_relations(10)` |
| `vikunja.add_task_relation(10, 11, "subtask")` | `vikunja.add_issue_relation(10, 11, "subtask")` |
| `vikunja.delete_task_relation(10, "subtask", 11)` | `vikunja.delete_issue_relation(10, "subtask", 11)` |
| `vikunja.list_task_reminders(10)` | `vikunja.list_issue_reminders(10)` |
| `vikunja.set_task_reminders(10, "...")` | `vikunja.set_issue_reminders(10, "...")` |

Also rename the test functions themselves for consistency (optional but clean):
`test_list_tasks_no_filter` → `test_list_issues_no_filter`, etc.

The complete updated `tests/test_vikunja.py`:

```python
import json
from unittest.mock import MagicMock, patch
from gateway.config import Config, VikunjaConfig
import gateway.tools.vikunja as vikunja


def test_vikunja_config_defaults():
    c = Config()
    assert c.vikunja.base_url == ""
    assert c.vikunja.api_token == ""


def test_vikunja_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_VIKUNJA__BASE_URL", "https://vikunja.example.com")
    monkeypatch.setenv("GATEWAY_VIKUNJA__API_TOKEN", "tok-abc123")
    c = Config()
    assert c.vikunja.base_url == "https://vikunja.example.com"
    assert c.vikunja.api_token == "tok-abc123"


def _make_mock_client():
    """Returns a mock httpx client usable as context manager."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


def test_client_raises_when_not_configured():
    vikunja.init(VikunjaConfig(base_url="", api_token=""))
    import pytest
    with pytest.raises(AssertionError):
        vikunja._client()


def test_list_projects():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0},
        {"id": 2, "title": "Work", "description": "Work issues", "is_archived": False, "parent_project_id": 0},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_projects())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "Inbox"


def test_get_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_project(1))
    assert result["id"] == 1
    mock_client.get.assert_called_once_with("/projects/1")


def test_create_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 3, "title": "New Project", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("New Project"))
    assert result["id"] == 3
    assert result["title"] == "New Project"
    mock_client.put.assert_called_once_with("/projects", json={"title": "New Project"})


def test_create_project_with_parent():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 4, "title": "Sub", "description": "desc", "is_archived": False, "parent_project_id": 1
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("Sub", description="desc", parent_project_id=1))
    assert result["parent_project_id"] == 1
    mock_client.put.assert_called_once_with(
        "/projects", json={"title": "Sub", "description": "desc", "parent_project_id": 1}
    )


def test_list_issues_no_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 10, "title": "Buy milk", "description": "", "done": False,
         "due_date": None, "priority": 0, "project_id": 1, "labels": []}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_issues())
    assert result[0]["id"] == 10
    mock_client.get.assert_called_once_with("/tasks", params={"sort_by": "id", "order_by": "asc", "page": 1})


def test_list_issues_with_project_id():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_issues(project_id=5)
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project = 5"


def test_list_issues_project_id_combined_with_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_issues(project_id=5, filter_by="done=false")
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project = 5 && done=false"


def test_get_issue():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [], "related_tasks": {}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_issue(10))
    assert result["id"] == 10
    mock_client.get.assert_called_once_with("/tasks/10")


def test_create_issue():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 11, "title": "New issue", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_issue(project_id=1, title="New issue"))
    assert result["id"] == 11
    mock_client.put.assert_called_once_with("/projects/1/tasks", json={"title": "New issue"})


def test_create_issue_defaults_to_inbox():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0},
        {"id": 2, "title": "Work", "description": "", "is_archived": False, "parent_project_id": 0},
    ]
    mock_client.put.return_value.json.return_value = {
        "id": 99, "title": "Quick capture", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_issue(title="Quick capture"))
    assert result["project_id"] == 1
    mock_client.get.assert_called_once_with("/projects")
    mock_client.put.assert_called_once_with("/projects/1/tasks", json={"title": "Quick capture"})


def test_create_issue_inbox_missing_raises():
    import pytest
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 2, "title": "Work", "description": "", "is_archived": False, "parent_project_id": 0},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        with pytest.raises(ValueError):
            vikunja.create_issue(title="Quick capture")


def test_update_issue_partial():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy oat milk", "done": False, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.update_issue(10, title="Buy oat milk"))
    assert result["title"] == "Buy oat milk"
    mock_client.post.assert_called_once_with("/tasks/10", json={"title": "Buy oat milk"})


def test_update_issue_done():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "done": True, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.update_issue(10, done="true")
    mock_client.post.assert_called_once_with("/tasks/10", json={"done": True})


def test_delete_issue():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "The issue was successfully deleted."}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_issue(10))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10")


def test_list_labels():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "urgent", "hex_color": "ff0000", "description": ""},
        {"id": 2, "title": "home", "hex_color": "", "description": ""},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_labels())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "urgent"
    mock_client.get.assert_called_once_with("/labels")


def test_add_issue_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {"label_id": 1, "created": "2024-01-01T00:00:00Z"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_issue_label(issue_id=10, label_id=1))
    assert result["status"] == "added"
    mock_client.put.assert_called_once_with("/tasks/10/labels", json={"label_id": 1})


def test_remove_issue_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.remove_issue_label(issue_id=10, label_id=1))
    assert result["status"] == "removed"
    mock_client.delete.assert_called_once_with("/tasks/10/labels/1")


def test_list_issue_comments():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "comment": "First note", "created": "2024-01-01T00:00:00Z",
         "author": {"username": "charlie"}}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_issue_comments(10))
    assert result[0]["id"] == 1
    assert result[0]["comment"] == "First note"
    mock_client.get.assert_called_once_with("/tasks/10/comments")


def test_add_issue_comment():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 2, "comment": "Follow up needed", "created": "2024-01-02T00:00:00Z",
        "author": {"username": "charlie"}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_issue_comment(10, "Follow up needed"))
    assert result["id"] == 2
    mock_client.put.assert_called_once_with("/tasks/10/comments", json={"comment": "Follow up needed"})


def test_list_issue_relations():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Issue A", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [],
        "related_tasks": {"subtask": [{"id": 11, "title": "Sub A"}]}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_issue_relations(10))
    assert "subtask" in result
    assert result["subtask"][0]["id"] == 11


def test_add_issue_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "task_id": 10, "other_task_id": 11, "relation_kind": "subtask", "created": "2024-01-01T00:00:00Z"
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_issue_relation(10, 11, "subtask"))
    assert result["status"] == "created"
    mock_client.put.assert_called_once_with(
        "/tasks/10/relations", json={"other_task_id": 11, "relation_kind": "subtask"}
    )


def test_delete_issue_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_issue_relation(10, "subtask", 11))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10/relations/subtask/11")


def test_list_issue_reminders():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Issue", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {},
        "reminders": [{"reminder": "2024-06-01T09:00:00Z", "relative_period": 0}]
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_issue_reminders(10))
    assert len(result) == 1
    assert result[0]["reminder"] == "2024-06-01T09:00:00Z"
    mock_client.get.assert_called_once_with("/tasks/10")


def test_set_issue_reminders():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Issue", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {},
        "reminders": [{"reminder": "2024-06-01T09:00:00Z", "relative_period": 0}]
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.set_issue_reminders(10, '[{"reminder": "2024-06-01T09:00:00Z"}]'))
    assert result["status"] == "updated"
    mock_client.post.assert_called_once_with(
        "/tasks/10", json={"reminders": [{"reminder": "2024-06-01T09:00:00Z"}]}
    )


def test_set_issue_reminders_empty_clears_all():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Issue", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {}, "reminders": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.set_issue_reminders(10, "[]")
    mock_client.post.assert_called_once_with("/tasks/10", json={"reminders": []})


def test_vikunja_registered_in_server():
    from gateway.config import Config
    from gateway import main

    config = Config()
    mcp = main.create_server(config)
    assert mcp is not None
```

- [ ] **Step 2: Update `tests/cli/test_vikunja.py`**

Complete updated file:

```python
from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

ISSUE = {"id": 42, "title": "Write tests", "done": False, "due_date": "2026-06-10T00:00:00Z", "priority": 2, "project_id": 1, "description": "", "labels": [], "reminders": [], "related_tasks": {}}
ISSUES = [ISSUE]
PROJECT = {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": None}
PROJECTS = [PROJECT]
COMMENTS = [{"id": 1, "comment": "Looks good", "created": "2026-06-07T10:00:00Z", "author": "charlie"}]

runner = CliRunner()


def test_issues_list():
    with patch("gateway.cli.client.call_tool", return_value=ISSUES) as mock:
        r = runner.invoke(main, ["issues", "list"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_issues", {"project_id": 0, "filter_by": "", "sort_by": "id", "order_by": "asc", "page": 1})


def test_issues_list_with_project():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["issues", "list", "--project", "5"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_issues", {"project_id": 5, "filter_by": "", "sort_by": "id", "order_by": "asc", "page": 1})


def test_issues_get():
    with patch("gateway.cli.client.call_tool", return_value=ISSUE) as mock:
        r = runner.invoke(main, ["issues", "get", "42"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_issue", {"issue_id": 42})


def test_issues_create():
    with patch("gateway.cli.client.call_tool", return_value=ISSUE) as mock:
        r = runner.invoke(main, ["issues", "create", "Write tests", "--project", "1"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_issue", {"project_id": 1, "title": "Write tests", "description": "", "due_date": "", "priority": ""})


def test_issues_create_defaults_to_inbox():
    with patch("gateway.cli.client.call_tool", return_value=ISSUE) as mock:
        r = runner.invoke(main, ["issues", "create", "Write tests"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_issue", {"project_id": 0, "title": "Write tests", "description": "", "due_date": "", "priority": ""})


def test_issues_delete():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "issue_id": 42}) as mock:
        r = runner.invoke(main, ["issues", "delete", "42"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_issue", {"issue_id": 42})


def test_issues_comments():
    with patch("gateway.cli.client.call_tool", return_value=COMMENTS) as mock:
        r = runner.invoke(main, ["issues", "comments", "42"])
    assert r.exit_code == 0
    assert "Looks good" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_issue_comments", {"issue_id": 42})


def test_issues_comment():
    with patch("gateway.cli.client.call_tool", return_value={"id": 2, "comment": "LGTM", "created": "2026-06-07"}) as mock:
        r = runner.invoke(main, ["issues", "comment", "42", "LGTM"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "add_issue_comment", {"issue_id": 42, "comment": "LGTM"})


def test_projects_list():
    with patch("gateway.cli.client.call_tool", return_value=PROJECTS) as mock:
        r = runner.invoke(main, ["projects", "list"])
    assert r.exit_code == 0
    assert "Inbox" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_projects", {})


def test_projects_create():
    with patch("gateway.cli.client.call_tool", return_value=PROJECT) as mock:
        r = runner.invoke(main, ["projects", "create", "My Project"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_project", {"title": "My Project", "description": "", "parent_project_id": 0})
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/charlie/Code/awfulwoman/gateway && .venv/bin/pytest tests/ -x -q 2>&1 | head -30
```

Expected: failures on `AttributeError: module 'gateway.tools.vikunja' has no attribute 'list_issues'` and similar.

---

## Task 2: Rename `gateway/tools/vikunja.py`

**Files:**
- Modify: `gateway/tools/vikunja.py`

- [ ] **Step 1: Replace `_task_summary` with `_issue_summary`**

```python
def _issue_summary(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "title": t.get("title", ""),
        "description": t.get("description", ""),
        "done": t.get("done", False),
        "due_date": t.get("due_date"),
        "priority": t.get("priority", 0),
        "project_id": t.get("project_id"),
        "labels": [{"id": l.get("id"), "title": l.get("title")} for l in (t.get("labels") or [])],
        "reminders": t.get("reminders") or [],
        "related_tasks": t.get("related_tasks") or {},
    }
```

- [ ] **Step 2: Rename `list_tasks` → `list_issues`**

```python
def list_issues(
    project_id: int = 0,
    filter_by: str = "",
    sort_by: str = "id",
    order_by: str = "asc",
    page: int = 1,
) -> str:
    """List Vikunja issues. project_id filters to a specific project. filter_by accepts Vikunja filter syntax e.g. 'done=false'. sort_by can be id, title, due_date, priority, created, updated. order_by is asc or desc."""
    params: dict = {"sort_by": sort_by, "order_by": order_by, "page": page}
    if project_id and filter_by:
        params["filter"] = f"project = {project_id} && {filter_by}"
    elif project_id:
        params["filter"] = f"project = {project_id}"
    elif filter_by:
        params["filter"] = filter_by
    with _client() as c:
        r = c.get("/tasks", params=params)
        r.raise_for_status()
    return json.dumps([_issue_summary(t) for t in r.json()])
```

- [ ] **Step 3: Rename `get_task` → `get_issue`**

```python
def get_issue(issue_id: int) -> str:
    """Get a Vikunja issue by ID. Returns full detail including labels, reminders, and related issues."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))
```

- [ ] **Step 4: Rename `create_task` → `create_issue`**

```python
def create_issue(
    project_id: int = 0,
    title: str = "",
    description: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Create a new Vikunja issue. If project_id is 0 (or omitted), the issue is created in the user's Inbox project. due_date is ISO 8601 (e.g. 2024-12-31T10:00:00Z). priority is 0 (none) through 5 (critical)."""
    if not project_id:
        project_id = _find_inbox_project_id()
    body: dict = {"title": title}
    if description:
        body["description"] = description
    if due_date:
        body["due_date"] = due_date
    if priority:
        body["priority"] = int(priority)
    with _client() as c:
        r = c.put(f"/projects/{project_id}/tasks", json=body)
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))
```

- [ ] **Step 5: Rename `update_task` → `update_issue`**

```python
def update_issue(
    issue_id: int,
    title: str = "",
    description: str = "",
    done: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Update a Vikunja issue. Only supplied (non-empty) fields are changed. done must be 'true' or 'false'. priority is 0-5."""
    body: dict = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if done in ("true", "false"):
        body["done"] = done == "true"
    if due_date:
        body["due_date"] = due_date
    if priority:
        body["priority"] = int(priority)
    if not body:
        return json.dumps({"status": "error", "message": "No fields to update"})
    with _client() as c:
        r = c.post(f"/tasks/{issue_id}", json=body)
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))
```

- [ ] **Step 6: Rename `delete_task` → `delete_issue`**

```python
def delete_issue(issue_id: int) -> str:
    """Delete a Vikunja issue by ID."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "issue_id": issue_id})
```

- [ ] **Step 7: Rename `add_task_label` → `add_issue_label` and `remove_task_label` → `remove_issue_label`**

```python
def add_issue_label(issue_id: int, label_id: int) -> str:
    """Attach a label to a Vikunja issue. Use list_labels to find label IDs."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/labels", json={"label_id": label_id})
        r.raise_for_status()
    return json.dumps({"status": "added", "issue_id": issue_id, "label_id": label_id})


def remove_issue_label(issue_id: int, label_id: int) -> str:
    """Remove a label from a Vikunja issue."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}/labels/{label_id}")
        r.raise_for_status()
    return json.dumps({"status": "removed", "issue_id": issue_id, "label_id": label_id})
```

- [ ] **Step 8: Rename `list_task_comments` → `list_issue_comments` and `add_task_comment` → `add_issue_comment`**

```python
def list_issue_comments(issue_id: int) -> str:
    """Get all comments on a Vikunja issue."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}/comments")
        r.raise_for_status()
    comments = [
        {
            "id": item.get("id"),
            "comment": item.get("comment", ""),
            "created": item.get("created"),
            "author": item.get("author", {}).get("username", ""),
        }
        for item in r.json()
    ]
    return json.dumps(comments)


def add_issue_comment(issue_id: int, comment: str) -> str:
    """Add a comment to a Vikunja issue."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/comments", json={"comment": comment})
        r.raise_for_status()
    data = r.json()
    return json.dumps({
        "id": data.get("id"),
        "comment": data.get("comment", ""),
        "created": data.get("created"),
    })
```

- [ ] **Step 9: Rename `list_task_relations` → `list_issue_relations`, `add_task_relation` → `add_issue_relation`, `delete_task_relation` → `delete_issue_relation`**

```python
def list_issue_relations(issue_id: int) -> str:
    """Get all relations for a Vikunja issue. Returns a dict keyed by relation kind (e.g. 'subtask', 'blocking')."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("related_tasks", {}))


def add_issue_relation(issue_id: int, other_issue_id: int, relation_kind: str) -> str:
    """Create a relation between two Vikunja issues. relation_kind: subtask, parenttask, related, duplicateof, duplicates, blocking, blocked, precedes, follows, copiedfrom, copiedto."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/relations", json={"other_task_id": other_issue_id, "relation_kind": relation_kind})
        r.raise_for_status()
    return json.dumps({"status": "created", "issue_id": issue_id, "other_issue_id": other_issue_id, "relation_kind": relation_kind})


def delete_issue_relation(issue_id: int, relation_kind: str, other_issue_id: int) -> str:
    """Remove a relation between two Vikunja issues. relation_kind and other_issue_id must match an existing relation."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}/relations/{relation_kind}/{other_issue_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "issue_id": issue_id, "relation_kind": relation_kind, "other_issue_id": other_issue_id})
```

- [ ] **Step 10: Rename `list_task_reminders` → `list_issue_reminders` and `set_task_reminders` → `set_issue_reminders`**

```python
def list_issue_reminders(issue_id: int) -> str:
    """Get all reminders for a Vikunja issue. Each reminder has a 'reminder' field (ISO 8601 datetime)."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("reminders", []))


def set_issue_reminders(issue_id: int, reminders_json: str) -> str:
    """Replace all reminders on a Vikunja issue. reminders_json is a JSON array of reminder objects, e.g. '[{"reminder": "2024-12-01T09:00:00Z"}]'. Pass '[]' to clear all reminders. Call list_issue_reminders first to see existing reminders before modifying."""
    reminders = json.loads(reminders_json)
    with _client() as c:
        r = c.post(f"/tasks/{issue_id}", json={"reminders": reminders})
        r.raise_for_status()
    return json.dumps({"status": "updated", "issue_id": issue_id, "reminders": r.json().get("reminders", [])})
```

- [ ] **Step 11: Update `register()` to list new function names**

```python
def register(mcp) -> None:
    for fn in [
        list_projects,
        get_project,
        create_project,
        list_issues,
        get_issue,
        create_issue,
        update_issue,
        delete_issue,
        list_labels,
        add_issue_label,
        remove_issue_label,
        list_issue_comments,
        add_issue_comment,
        list_issue_relations,
        add_issue_relation,
        delete_issue_relation,
        list_issue_reminders,
        set_issue_reminders,
    ]:
        mcp.tool()(fn)
```

- [ ] **Step 12: Run tests to confirm `tests/test_vikunja.py` now passes**

```bash
cd /Users/charlie/Code/awfulwoman/gateway && .venv/bin/pytest tests/test_vikunja.py -v
```

Expected: all tests in `tests/test_vikunja.py` PASS. `tests/cli/test_vikunja.py` still fails.

---

## Task 3: Rename fmt helpers

**Files:**
- Modify: `gateway/cli/fmt.py`

- [ ] **Step 1: Rename `tasks()` → `issues()` and `task_detail()` → `issue_detail()`**

Replace the two functions (lines 150–174):

```python
def issues(data: list) -> str:
    if not data:
        return "No issues."
    lines = []
    for t in data:
        done = "x" if t.get("done") else " "
        due = f"  due:{t['due_date'][:10]}" if t.get("due_date") else ""
        pri = f"  p{t['priority']}" if t.get("priority") else ""
        lines.append(f"[{done}] #{t['id']}  {t['title']}{due}{pri}")
    return "\n".join(lines)


def issue_detail(t: dict) -> str:
    lines = [
        f"#{t['id']} {t['title']}",
        f"  Done:     {'yes' if t.get('done') else 'no'}",
        f"  Priority: {t.get('priority', 0)}",
        f"  Due:      {t.get('due_date') or '-'}",
        f"  Project:  {t.get('project_id') or '-'}",
    ]
    if t.get("description"):
        lines += ["", t["description"]]
    if t.get("labels"):
        lines.append(f"  Labels:   {', '.join(l['title'] for l in t['labels'])}")
    return "\n".join(lines)
```

---

## Task 4: Update CLI commands and registration

**Files:**
- Modify: `gateway/cli/commands/vikunja.py`
- Modify: `gateway/cli/__init__.py`

- [ ] **Step 1: Update group docstring and all command functions in `gateway/cli/commands/vikunja.py`**

Replace the entire issues section of the file (everything from `@click.group()` through `remove_label`). The complete replacement for the `tasks_group` portion of the file (leave `projects_group` section unchanged):

```python
@click.group()
def tasks_group() -> None:
    """Issues (Vikunja)."""


@tasks_group.command("list")
@click.option("--project", "project_id", default=0, type=int)
@click.option("--filter", "filter_by", default="")
@click.option("--sort", "sort_by", default="id", type=click.Choice(["id", "title", "due_date", "priority", "created", "updated"]))
@click.option("--order", "order_by", default="asc", type=click.Choice(["asc", "desc"]))
@click.option("--page", default=1)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_issues(obj: dict, project_id: int, filter_by: str, sort_by: str, order_by: str, page: int, as_json: bool) -> None:
    """List issues."""
    try:
        data = client.call_tool(obj["server"], "list_issues", {"project_id": project_id, "filter_by": filter_by, "sort_by": sort_by, "order_by": order_by, "page": page})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issues(data))


@tasks_group.command("get")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Get an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "get_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issue_detail(data))


@tasks_group.command("create")
@click.argument("title")
@click.option("--project", "project_id", default=0, type=int, help="Project ID; omit to create in Inbox.")
@click.option("--description", default="")
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_issue(obj: dict, project_id: int, title: str, description: str, due_date: str, priority: str, as_json: bool) -> None:
    """Create an issue. Defaults to Inbox if --project is not given."""
    try:
        data = client.call_tool(obj["server"], "create_issue", {"project_id": project_id, "title": title, "description": description, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")


@tasks_group.command("update")
@click.argument("issue-id", type=int)
@click.option("--title", default="")
@click.option("--description", default="")
@click.option("--done", "done", default="", type=click.Choice(["true", "false", ""]))
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update_issue(obj: dict, issue_id: int, title: str, description: str, done: str, due_date: str, priority: str, as_json: bool) -> None:
    """Update an issue. Only supplied options are changed."""
    try:
        data = client.call_tool(obj["server"], "update_issue", {"issue_id": issue_id, "title": title, "description": description, "done": done, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: #{issue_id}")


@tasks_group.command("delete")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Delete an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "delete_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: #{issue_id}")


@tasks_group.command("comments")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_comments(obj: dict, issue_id: int, as_json: bool) -> None:
    """List comments on an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_comments", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.comments(data))


@tasks_group.command("comment")
@click.argument("issue-id", type=int)
@click.argument("comment")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_comment(obj: dict, issue_id: int, comment: str, as_json: bool) -> None:
    """Add a comment to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_issue_comment", {"issue_id": issue_id, "comment": comment})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Comment added: #{data.get('id')}")


@tasks_group.command("relations")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_relations(obj: dict, issue_id: int, as_json: bool) -> None:
    """List relations for an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_relations", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json_mod.dumps(data, indent=2))
    elif not data:
        click.echo("No relations.")
    else:
        lines = [f"  {kind}: #{t.get('id')} {t.get('title', '')}" for kind, issues in data.items() for t in issues]
        click.echo("\n".join(lines))


@tasks_group.command("add-relation")
@click.argument("issue-id", type=int)
@click.argument("other-issue-id", type=int)
@click.argument("kind")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_relation(obj: dict, issue_id: int, other_issue_id: int, kind: str, as_json: bool) -> None:
    """Add a relation between two issues. KIND: subtask, parenttask, related, blocking, blocked, precedes, follows."""
    try:
        data = client.call_tool(obj["server"], "add_issue_relation", {"issue_id": issue_id, "other_issue_id": other_issue_id, "relation_kind": kind})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation added: #{issue_id} {kind} #{other_issue_id}")


@tasks_group.command("remove-relation")
@click.argument("issue-id", type=int)
@click.argument("kind")
@click.argument("other-issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_relation(obj: dict, issue_id: int, kind: str, other_issue_id: int, as_json: bool) -> None:
    """Remove a relation between two issues."""
    try:
        data = client.call_tool(obj["server"], "delete_issue_relation", {"issue_id": issue_id, "relation_kind": kind, "other_issue_id": other_issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation removed: #{issue_id} {kind} #{other_issue_id}")


@tasks_group.command("reminders")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_reminders(obj: dict, issue_id: int, as_json: bool) -> None:
    """List reminders for an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_reminders", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else ("\n".join(r.get("reminder", "") for r in data) if data else "No reminders."))


@tasks_group.command("set-reminders")
@click.argument("issue-id", type=int)
@click.argument("reminders-json")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def set_reminders(obj: dict, issue_id: int, reminders_json: str, as_json: bool) -> None:
    """Replace all reminders on an issue. REMINDERS-JSON: '[{"reminder":"2026-06-10T09:00:00Z"}]' or '[]' to clear."""
    try:
        data = client.call_tool(obj["server"], "set_issue_reminders", {"issue_id": issue_id, "reminders_json": reminders_json})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Reminders updated: #{issue_id}")


@tasks_group.command("labels")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_labels(obj: dict, as_json: bool) -> None:
    """List all available labels."""
    try:
        data = client.call_tool(obj["server"], "list_labels", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else ("\n".join(f"#{lbl['id']}  {lbl['title']}" for lbl in data) if data else "No labels."))


@tasks_group.command("add-label")
@click.argument("issue-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_label(obj: dict, issue_id: int, label_id: int, as_json: bool) -> None:
    """Attach a label to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_issue_label", {"issue_id": issue_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} added to issue #{issue_id}")


@tasks_group.command("remove-label")
@click.argument("issue-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_label(obj: dict, issue_id: int, label_id: int, as_json: bool) -> None:
    """Remove a label from an issue."""
    try:
        data = client.call_tool(obj["server"], "remove_issue_label", {"issue_id": issue_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} removed from issue #{issue_id}")
```

- [ ] **Step 2: Update CLI registration in `gateway/cli/__init__.py`**

Change line 28:

```python
main.add_command(vikunja.tasks_group, "issues")
```

(The `tasks_group` Python object name is internal and doesn't need renaming.)

---

## Task 5: Run full test suite and commit

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/charlie/Code/awfulwoman/gateway && .venv/bin/pytest tests/ -v
```

Expected: all tests PASS. If any fail, fix before proceeding.

- [ ] **Step 2: Commit**

```bash
cd /Users/charlie/Code/awfulwoman/gateway
git add gateway/tools/vikunja.py gateway/cli/commands/vikunja.py gateway/cli/__init__.py gateway/cli/fmt.py tests/test_vikunja.py tests/cli/test_vikunja.py
git commit -m "$(cat <<'EOF'
feat: rename tasks to issues in MCP tools and CLI

Renames all user-facing "task" terminology to "issue" across Vikunja
MCP tool names, CLI commands, parameters, formatters, and tests.
Apple Reminders covers personal to-dos; Vikunja items are project issues.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update skill doc

**Files:**
- Modify: `skills/gateway-cli/SKILL.md`

- [ ] **Step 1: Update `skills/gateway-cli/SKILL.md`**

There are occurrences of `gw tasks` / `TASK_ID` in multiple places in this file — the frontmatter description, the global-flags example (line 44), the command-reference section, and the common-patterns section at the bottom. All must be updated.

Replace the description line in the frontmatter:

```yaml
description: Use gw CLI commands to interact with gateway services (calendar, email, notes, issues, bookmarks, location, contacts, reminders) from the shell. Use instead of MCP tools when scripting, piping output, or wanting human-readable inspection.
```

Replace the section header:

```markdown
### `gw issues`
```

Replace the command reference block under that header:

```bash
gw issues list [--project ID] [--filter EXPR] [--sort id|title|due_date|priority|created|updated] \
    [--order asc|desc] [--page N]
gw issues get ISSUE_ID
gw issues create TITLE [--project ID] [--description TEXT] [--due TEXT] [--priority TEXT]
gw issues update ISSUE_ID [--title TEXT] [--description TEXT] [--done true|false] \
    [--due TEXT] [--priority TEXT]
gw issues delete ISSUE_ID
gw issues comments ISSUE_ID
gw issues comment ISSUE_ID COMMENT
gw issues relations ISSUE_ID
gw issues add-relation ISSUE_ID OTHER_ISSUE_ID KIND
gw issues remove-relation ISSUE_ID KIND OTHER_ISSUE_ID
gw issues reminders ISSUE_ID
gw issues set-reminders ISSUE_ID REMINDERS_JSON
gw issues labels
gw issues add-label ISSUE_ID LABEL_ID
gw issues remove-label ISSUE_ID LABEL_ID
```

Replace the examples block under that header:

```bash
# examples
gw issues list --project 3 --sort due_date --order asc
gw issues list --filter "title = bug"
gw issues get 42
gw issues create "Fix login bug" --project 3 --due "2026-06-10" --priority high
gw issues create "Quick capture"                     # -> Inbox
gw issues update 42 --done true
gw issues comment 42 "Investigated — root cause is JWT expiry"
gw issues add-relation 42 101 blocking
gw issues set-reminders 42 '[{"reminder":"2026-06-10T09:00:00Z"}]'
gw issues set-reminders 42 '[]'
gw issues labels
gw issues add-label 42 7
gw issues list --project 3 --json | jq '.[] | select(.done == false) | .title'
```

Also update the Common patterns section at the bottom — replace the tasks example:

```bash
# Find overdue issues and extract titles
gw issues list --sort due_date --order asc --json | jq '.[] | select(.done == false) | .title'
```

Also replace the global-flags section example (currently line ~44):

```bash
gw issues list --project 3 --json
```

And the end-to-end example:

```bash
# Create an issue and immediately set a reminder
ISSUE_ID=$(gw issues create "Deploy v2" --project 3 --json | jq -r '.id')
gw issues set-reminders $ISSUE_ID '[{"reminder":"2026-06-10T08:00:00Z"}]'
```

After editing, verify no remaining `gw tasks` or `TASK_ID` remain:

```bash
grep -n "gw tasks\|TASK_ID" /Users/charlie/Code/awfulwoman/gateway/skills/gateway-cli/SKILL.md
```

Expected: no output.

- [ ] **Step 2: Commit skill doc**

```bash
cd /Users/charlie/Code/awfulwoman/gateway
git add skills/gateway-cli/SKILL.md
git commit -m "$(cat <<'EOF'
docs: update gateway-cli skill to use issues terminology

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Sync skill to Chezmoi**

The skill is also installed to `~/.claude/skills/gateway-cli/SKILL.md`. Update and add to Chezmoi:

```bash
cp /Users/charlie/Code/awfulwoman/gateway/skills/gateway-cli/SKILL.md ~/.claude/skills/gateway-cli/SKILL.md
chezmoi add ~/.claude/skills/gateway-cli/SKILL.md
```
