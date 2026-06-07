from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

BM_RESULT = {"bookmarks": [{"id": "abc123", "title": "Python docs", "url": "https://docs.python.org", "type": "link", "tags": ["python"], "favourited": False, "archived": False, "created_at": None, "note": None, "summary": ""}], "next_cursor": None}
BM = BM_RESULT["bookmarks"][0]
TAGS = [{"id": "t1", "name": "python", "count": 5}]
LISTS = [{"id": "l1", "name": "Reading", "icon": "📚", "parent_id": None}]

runner = CliRunner()


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=BM_RESULT) as mock:
        r = runner.invoke(main, ["bookmarks", "search", "python"])
    assert r.exit_code == 0
    assert "Python docs" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_bookmarks", {"query": "python", "limit": 10, "cursor": ""})


def test_get():
    with patch("gateway.cli.client.call_tool", return_value=BM) as mock:
        r = runner.invoke(main, ["bookmarks", "get", "abc123"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_bookmark", {"bookmark_id": "abc123"})


def test_create_link():
    with patch("gateway.cli.client.call_tool", return_value={"status": "created", "bookmark": BM}) as mock:
        r = runner.invoke(main, ["bookmarks", "create", "https://example.com"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_bookmark", {"type": "link", "content": "https://example.com", "title": ""})


def test_tags():
    with patch("gateway.cli.client.call_tool", return_value=TAGS) as mock:
        r = runner.invoke(main, ["bookmarks", "tags"])
    assert r.exit_code == 0
    assert "python" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_tags", {})


def test_lists():
    with patch("gateway.cli.client.call_tool", return_value=LISTS) as mock:
        r = runner.invoke(main, ["bookmarks", "lists"])
    assert r.exit_code == 0
    assert "Reading" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_lists", {})
