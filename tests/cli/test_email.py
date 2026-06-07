from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

EMAILS = [{"message_id": "<abc@x>", "from": "bob@example.com", "to": "me@x.com", "subject": "Hello", "date": "Sun, 07 Jun 2026 10:00:00"}]
EMAIL_BODY = {"message_id": "<abc@x>", "from": "bob@example.com", "to": "me@x.com", "subject": "Hello", "date": "Sun, 07 Jun 2026 10:00:00", "body": "Hi there!"}
FOLDERS = ["INBOX", "Sent", "Drafts"]

runner = CliRunner()


def test_folders():
    with patch("gateway.cli.client.call_tool", return_value=FOLDERS) as mock:
        r = runner.invoke(main, ["email", "folders"])
    assert r.exit_code == 0
    assert "INBOX" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_folders", {})


def test_list_emails():
    with patch("gateway.cli.client.call_tool", return_value=EMAILS) as mock:
        r = runner.invoke(main, ["email", "list"])
    assert r.exit_code == 0
    assert "Hello" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_emails", {"folder": "INBOX", "max_count": 20})


def test_list_emails_custom_folder():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["email", "list", "--folder", "Sent", "--limit", "5"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_emails", {"folder": "Sent", "max_count": 5})


def test_unread():
    with patch("gateway.cli.client.call_tool", return_value=EMAILS) as mock:
        r = runner.invoke(main, ["email", "unread"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "fetch_unread_emails", {"max_count": 10})


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=EMAILS) as mock:
        r = runner.invoke(main, ["email", "search", "invoice"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_emails", {"query": "invoice", "search_in": "all", "folder": "INBOX", "max_results": 20})


def test_read():
    with patch("gateway.cli.client.call_tool", return_value=EMAIL_BODY) as mock:
        r = runner.invoke(main, ["email", "read", "<abc@x>"])
    assert r.exit_code == 0
    assert "Hi there!" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "fetch_email_body", {"message_id": "<abc@x>"})


def test_mark_read():
    with patch("gateway.cli.client.call_tool", return_value={"status": "marked_read"}) as mock:
        r = runner.invoke(main, ["email", "mark-read", "<abc@x>"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "mark_email_read", {"message_id": "<abc@x>"})
