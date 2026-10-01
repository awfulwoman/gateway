from __future__ import annotations
import json
import pytest
import gateway.tools.email as email
from gateway.config import MailArchiveServerConfig

PERSONAL_MSG = {
    "id": "m1", "account": "personal", "message_id": "<a@b.com>",
    "folder": "INBOX", "from": "Alice <alice@example.com>", "to": "charlie@example.com",
    "subject": "Hello", "date": "2026-09-01T09:15:04Z", "seen": False, "deleted": False,
    "size_bytes": 1000, "has_attachment": False, "attachments": [], "body_preview": "preview",
    "body": "Full body text.",
}
WORK_MSG = {
    "id": "m2", "account": "work", "message_id": "<c@d.com>",
    "folder": "INBOX", "from": "Bob <bob@example.com>", "to": "charlie@example.com",
    "subject": "Meeting", "date": "2026-09-02T09:15:04Z", "seen": True, "deleted": False,
    "size_bytes": 500, "has_attachment": False, "attachments": [], "body_preview": "preview",
    "body": "Meeting details.",
}


@pytest.fixture
def en(mail_archive_server, mail_archive_server_token):
    base_url, fake = mail_archive_server
    fake.seed(mail_archive_server_token, [PERSONAL_MSG, WORK_MSG])
    email.init(MailArchiveServerConfig(base_url=base_url, bearer_token=mail_archive_server_token))
    return email


def test_search_emails_returns_matches_and_next_cursor(en):
    result = json.loads(en.search_emails())
    assert result["total"] == 2
    assert len(result["messages"]) == 2
    assert result["next_cursor"] is None
    assert "stale_seconds" in result


def test_search_emails_scoped_to_one_account(en):
    result = json.loads(en.search_emails(account="personal"))
    assert result["total"] == 1
    assert result["messages"][0]["account"] == "personal"


def test_search_emails_since_until(en):
    result = json.loads(en.search_emails(since="2026-09-02"))
    assert result["total"] == 1
    assert result["messages"][0]["id"] == "m2"


def test_list_emails_is_a_plain_date_ordered_listing(en):
    result = json.loads(en.list_emails())
    assert [m["id"] for m in result["messages"]] == ["m2", "m1"]  # date_desc default


def test_fetch_email_body_by_archive_id(en):
    result = json.loads(en.fetch_email_body("m1"))
    assert result["body"] == "Full body text."


def test_fetch_email_body_unknown_id(en):
    result = json.loads(en.fetch_email_body("doesnotexist"))
    assert "error" in result


def test_mark_email_read_sets_seen_and_reports_upstream_status(en):
    result = json.loads(en.mark_email_read("m1"))
    assert result["seen"] is True
    assert result["upstream_synced"] is False


def test_mark_email_read_unknown_id(en):
    result = json.loads(en.mark_email_read("doesnotexist"))
    assert "error" in result


def test_list_email_accounts(en):
    result = json.loads(en.list_email_accounts())
    names = {a["name"] for a in result}
    assert names == {"personal", "work"}


def test_fetch_unread_emails_one_account_failing_does_not_block_the_others(mail_archive_server, mail_archive_server_token):
    base_url, fake = mail_archive_server
    fake.seed(mail_archive_server_token, [PERSONAL_MSG])
    email.init(MailArchiveServerConfig(
        base_url=base_url, bearer_token=mail_archive_server_token, accounts=["personal", "ghost"],
    ))

    result = json.loads(email.fetch_unread_emails())

    assert [m["id"] for m in result["messages"]] == ["m1"]
    assert len(result["errors"]) == 1
    assert result["errors"][0]["account"] == "ghost"


def test_fetch_unread_emails_syncs_each_configured_account_then_lists_unseen(en, mail_archive_server):
    _, fake = mail_archive_server

    result = json.loads(en.fetch_unread_emails())

    assert [m["id"] for m in result["messages"]] == ["m1"]
    assert result["errors"] == []
    assert {"personal", "work"} <= set(fake.sync_calls)
