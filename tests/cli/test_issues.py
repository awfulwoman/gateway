from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

ISSUE_SUMMARY = {
    "id": 42, "title": "Write tests", "project": "Gateway",
    "status": "open", "priority": 2, "due": "2026-07-01", "labels": ["dev"],
}
ISSUE_DETAIL = {
    **ISSUE_SUMMARY,
    "reminders": [], "related": [],
    "description": "Write unit tests",
    "checklist": [{"text": "Draft tests", "done": False}],
    "comments": [{"timestamp": "2026-06-16T10:00", "text": "Started"}],
}
ISSUES = [ISSUE_SUMMARY]

runner = CliRunner()


def test_issues_list():
    with patch("gateway.cli.client.call_tool", return_value=ISSUES) as mock:
        r = runner.invoke(main, ["issues", "list"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "", "status": "", "priority": -1, "label": ""},
    )


def test_issues_list_with_project():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["issues", "list", "--project", "Gateway"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "Gateway", "status": "", "priority": -1, "label": ""},
    )


def test_issues_list_with_status():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["issues", "list", "--status", "open"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "", "status": "open", "priority": -1, "label": ""},
    )


def test_issues_get():
    with patch("gateway.cli.client.call_tool", return_value=ISSUE_DETAIL) as mock:
        r = runner.invoke(main, ["issues", "get", "42"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "get_issue", {"issue_id": 42},
    )


def test_issues_create():
    with patch("gateway.cli.client.call_tool", return_value={"id": 43, "title": "New issue", "path": "Projects/_issues/0043-new-issue.md"}) as mock:
        r = runner.invoke(main, ["issues", "create", "New issue", "--project", "Gateway"])
    assert r.exit_code == 0
    assert "43" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "create_issue",
        {"title": "New issue", "project": "Gateway", "description": "", "due": "", "priority": 0, "labels": []},
    )


def test_issues_create_with_label():
    with patch("gateway.cli.client.call_tool", return_value={"id": 44, "title": "Bug", "path": "Projects/_issues/0044-bug.md"}) as mock:
        runner.invoke(main, ["issues", "create", "Bug", "--label", "bug", "--label", "urgent"])
    args = mock.call_args[0]
    assert args[2]["labels"] == ["bug", "urgent"]


def test_issues_update():
    with patch("gateway.cli.client.call_tool", return_value={"status": "updated", "id": 42}) as mock:
        r = runner.invoke(main, ["issues", "update", "42", "--status", "done"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "update_issue",
        {"issue_id": 42, "title": "", "status": "done", "project": "", "description": "", "due": "", "priority": -1},
    )


def test_issues_delete():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "id": 42}) as mock:
        r = runner.invoke(main, ["issues", "delete", "42"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "delete_issue", {"issue_id": 42},
    )
