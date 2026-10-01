from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

MESSAGES_ENVELOPE = {
    "messages": [{"id": "m1", "account": "personal", "from": "bob@example.com", "to": "me@x.com",
                  "subject": "Hello", "date": "2026-06-07T10:00:00Z"}],
    "total": 1, "next_cursor": None, "stale_seconds": 60,
}
EMAIL_BODY = {"id": "m1", "account": "personal", "from": "bob@example.com", "to": "me@x.com",
              "subject": "Hello", "date": "2026-06-07T10:00:00Z", "body": "Hi there!"}

runner = CliRunner()


def test_list_emails():
    with patch("gateway.cli.client.call_tool", return_value=MESSAGES_ENVELOPE) as mock:
        r = runner.invoke(main, ["email", "list"])
    assert r.exit_code == 0
    assert "Hello" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_emails",
        {"account": "", "since": "", "until": "", "order": "date_desc", "cursor": "", "limit": 20},
    )


def test_list_emails_with_account_and_cursor():
    with patch("gateway.cli.client.call_tool", return_value={"messages": [], "next_cursor": None}) as mock:
        runner.invoke(main, ["email", "list", "--account", "work", "--cursor", "abc123", "--limit", "5"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_emails",
        {"account": "work", "since": "", "until": "", "order": "date_desc", "cursor": "abc123", "limit": 5},
    )


def test_unread():
    with patch("gateway.cli.client.call_tool", return_value=MESSAGES_ENVELOPE) as mock:
        r = runner.invoke(main, ["email", "unread"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "fetch_unread_emails", {"limit": 10})


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=MESSAGES_ENVELOPE) as mock:
        r = runner.invoke(main, ["email", "search", "invoice"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "search_emails",
        {"query": "invoice", "account": "", "sender": "", "subject": "", "since": "", "until": "",
         "order": "date_desc", "cursor": "", "limit": 20},
    )


def test_search_with_since_until_and_sender():
    with patch("gateway.cli.client.call_tool", return_value={"messages": [], "next_cursor": None}) as mock:
        runner.invoke(main, ["email", "search", "invoice", "--since", "2026-01-01", "--until", "2026-02-01",
                              "--sender", "bob@example.com"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "search_emails",
        {"query": "invoice", "account": "", "sender": "bob@example.com", "subject": "", "since": "2026-01-01",
         "until": "2026-02-01", "order": "date_desc", "cursor": "", "limit": 20},
    )


def test_read():
    with patch("gateway.cli.client.call_tool", return_value=EMAIL_BODY) as mock:
        r = runner.invoke(main, ["email", "read", "m1"])
    assert r.exit_code == 0
    assert "Hi there!" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "fetch_email_body", {"id": "m1"})


def test_mark_read():
    with patch("gateway.cli.client.call_tool", return_value={"id": "m1", "account": "personal", "seen": True,
                                                              "upstream_synced": False}) as mock:
        r = runner.invoke(main, ["email", "mark-read", "m1"])
    assert r.exit_code == 0
    assert "not yet" in r.output.lower() or "local" in r.output.lower()
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "mark_email_read", {"id": "m1"})


def test_accounts():
    with patch("gateway.cli.client.call_tool", return_value=[{"name": "personal", "messages": 10}]) as mock:
        r = runner.invoke(main, ["email", "accounts"])
    assert r.exit_code == 0
    assert "personal" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_email_accounts", {})
