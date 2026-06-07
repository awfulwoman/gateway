from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

NOTES = ["Daily/2026-06-07.md", "Projects/Gateway.md"]
NOTE = {"path": "Projects/Gateway.md", "content": "# Gateway\n\nNotes here."}
SEARCH = [{"path": "Projects/Gateway.md", "match_type": "content", "line": 3, "context": "some matching line"}]

runner = CliRunner()


def test_list_notes():
    with patch("gateway.cli.client.call_tool", return_value=NOTES) as mock:
        r = runner.invoke(main, ["notes", "list"])
    assert r.exit_code == 0
    assert "Gateway.md" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_notes", {"folder": ""})


def test_list_notes_folder():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["notes", "list", "--folder", "Projects"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_notes", {"folder": "Projects"})


def test_read_note():
    with patch("gateway.cli.client.call_tool", return_value=NOTE) as mock:
        r = runner.invoke(main, ["notes", "read", "Projects/Gateway.md"])
    assert r.exit_code == 0
    assert "Notes here." in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "read_note", {"path": "Projects/Gateway.md"})


def test_search_notes():
    with patch("gateway.cli.client.call_tool", return_value=SEARCH) as mock:
        r = runner.invoke(main, ["notes", "search", "matching"])
    assert r.exit_code == 0
    assert "Gateway.md" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_notes", {"query": "matching", "folder": ""})


def test_create_note():
    with patch("gateway.cli.client.call_tool", return_value={"status": "created", "path": "New.md"}) as mock:
        r = runner.invoke(main, ["notes", "create", "New.md", "# New\n\nContent here."])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_note", {"path": "New.md", "content": "# New\n\nContent here."})


def test_delete_note():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "path": "Old.md"}) as mock:
        r = runner.invoke(main, ["notes", "delete", "Old.md"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_note", {"path": "Old.md"})
