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
