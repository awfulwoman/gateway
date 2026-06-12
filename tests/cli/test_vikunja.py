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
