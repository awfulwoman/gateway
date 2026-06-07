from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

REMINDERS = [{"title": "Buy milk", "completed": False, "due": "2026-06-08", "notes": "", "priority": 0, "list": "Shopping"}]
LISTS = [{"name": "Shopping", "id": "r1"}]

runner = CliRunner()


def test_list_reminders():
    with patch("gateway.cli.client.call_tool", return_value=REMINDERS):
        r = runner.invoke(main, ["reminders", "list"])
    assert r.exit_code == 0
    assert "Buy milk" in r.output


def test_list_reminders_passes_args():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["reminders", "list", "--list", "Shopping", "--completed"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_reminders", {"include_completed": True, "list_name": "Shopping"})


def test_list_reminder_lists():
    with patch("gateway.cli.client.call_tool", return_value=LISTS):
        r = runner.invoke(main, ["reminders", "lists"])
    assert r.exit_code == 0
    assert "Shopping" in r.output


def test_search_reminders():
    with patch("gateway.cli.client.call_tool", return_value=REMINDERS) as mock:
        r = runner.invoke(main, ["reminders", "search", "milk"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_reminders", {"query": "milk"})


def test_create_reminder():
    result = {"status": "created", "title": "Buy milk"}
    with patch("gateway.cli.client.call_tool", return_value=result) as mock:
        r = runner.invoke(main, ["reminders", "create", "Buy milk", "--list", "Shopping"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_reminder", {
        "title": "Buy milk", "due_iso": "", "notes": "", "list_name": "Shopping",
        "priority": 0, "location_name": "", "arrive_or_leave": "arrive",
    })


def test_complete_reminder():
    with patch("gateway.cli.client.call_tool", return_value={"status": "completed", "title": "Buy milk"}) as mock:
        r = runner.invoke(main, ["reminders", "complete", "Buy milk"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "complete_reminder", {"title": "Buy milk"})


def test_delete_reminder():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "title": "Buy milk"}) as mock:
        r = runner.invoke(main, ["reminders", "delete", "Buy milk"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_reminder", {"title": "Buy milk"})
