from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

TASK = {"id": 42, "title": "Write tests", "done": False, "due_date": "2026-06-10T00:00:00Z", "priority": 2, "project_id": 1, "description": "", "labels": [], "reminders": [], "related_tasks": {}}
TASKS = [TASK]
PROJECT = {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": None}
PROJECTS = [PROJECT]
COMMENTS = [{"id": 1, "comment": "Looks good", "created": "2026-06-07T10:00:00Z", "author": "charlie"}]

runner = CliRunner()


def test_tasks_list():
    with patch("gateway.cli.client.call_tool", return_value=TASKS) as mock:
        r = runner.invoke(main, ["tasks", "list"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_tasks", {"project_id": 0, "filter_by": "", "sort_by": "id", "order_by": "asc", "page": 1})


def test_tasks_list_with_project():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["tasks", "list", "--project", "5"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_tasks", {"project_id": 5, "filter_by": "", "sort_by": "id", "order_by": "asc", "page": 1})


def test_tasks_get():
    with patch("gateway.cli.client.call_tool", return_value=TASK) as mock:
        r = runner.invoke(main, ["tasks", "get", "42"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_task", {"task_id": 42})


def test_tasks_create():
    with patch("gateway.cli.client.call_tool", return_value=TASK) as mock:
        r = runner.invoke(main, ["tasks", "create", "1", "Write tests"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_task", {"project_id": 1, "title": "Write tests", "description": "", "due_date": "", "priority": ""})


def test_tasks_delete():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "task_id": 42}) as mock:
        r = runner.invoke(main, ["tasks", "delete", "42"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_task", {"task_id": 42})


def test_tasks_comments():
    with patch("gateway.cli.client.call_tool", return_value=COMMENTS) as mock:
        r = runner.invoke(main, ["tasks", "comments", "42"])
    assert r.exit_code == 0
    assert "Looks good" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_task_comments", {"task_id": 42})


def test_tasks_comment():
    with patch("gateway.cli.client.call_tool", return_value={"id": 2, "comment": "LGTM", "created": "2026-06-07"}) as mock:
        r = runner.invoke(main, ["tasks", "comment", "42", "LGTM"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "add_task_comment", {"task_id": 42, "comment": "LGTM"})


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
