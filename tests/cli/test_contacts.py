from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

CONTACTS = [{"name": "Alice Smith", "nickname": "", "organisation": "ACME", "job_title": "", "emails": ["alice@example.com"], "phones": ["+1 555-1234"], "addresses": [], "birthday": None, "urls": [], "note": ""}]

runner = CliRunner()


def test_lookup():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "lookup", "Alice"])
    assert r.exit_code == 0
    assert "Alice Smith" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "lookup_contact", {"name": "Alice"})


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "search", "alice@example.com"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_contacts", {"query": "alice@example.com"})


def test_list_contacts():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "list"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_contacts", {"limit": 50})
