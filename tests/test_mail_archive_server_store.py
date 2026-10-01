from __future__ import annotations
import pytest
import gateway.mail_archive_server.store as store
from gateway.config import MailArchiveServerConfig

MESSAGE = {
    "id": "m1", "account": "personal", "message_id": "<a@b.com>",
    "folder": "INBOX", "from": "Alice <alice@example.com>", "to": "charlie@example.com",
    "subject": "Hello", "date": "2026-09-01T09:15:04Z", "seen": False, "deleted": False,
    "size_bytes": 1000, "has_attachment": False, "attachments": [], "body_preview": "preview",
}


@pytest.fixture
def mas(mail_archive_server, mail_archive_server_token):
    base_url, fake = mail_archive_server
    fake.seed(mail_archive_server_token, [MESSAGE])
    store.init(MailArchiveServerConfig(base_url=base_url, bearer_token=mail_archive_server_token))
    return store


def test_search_returns_the_envelope(mas):
    result = mas.search()
    assert result["total"] == 1
    assert result["messages"][0]["subject"] == "Hello"


def test_search_passes_through_params(mas, mail_archive_server):
    base_url, fake = mail_archive_server
    result = mas.search(account="personal", seen=False)
    assert result["total"] == 1
    result2 = mas.search(account="work")
    assert result2["total"] == 0


def test_get_message_found(mas):
    assert mas.get_message("m1")["subject"] == "Hello"


def test_get_message_not_found_returns_none(mas):
    assert mas.get_message("doesnotexist") is None


def test_mark_read(mas):
    result = mas.mark_read("m1")
    assert result["seen"] is True
    assert result["upstream_synced"] is False


def test_mark_read_not_found_returns_none(mas):
    assert mas.mark_read("doesnotexist") is None


def test_accounts(mas):
    accounts = mas.accounts()
    assert accounts == [{"name": "personal", "messages": 1, "last_sync_attempt_at": "2026-01-01T00:00:00Z",
                          "last_sync_ok": True}]


def test_sync(mas):
    mas.sync()  # no account -- should not raise
    mas.sync(account="personal")


def test_sync_unknown_account_raises(mas):
    with pytest.raises(store.MailArchiveError):
        mas.sync(account="ghost")


def test_missing_token_raises(mail_archive_server):
    base_url, fake = mail_archive_server
    store.init(MailArchiveServerConfig(base_url=base_url, bearer_token=""))
    with pytest.raises(store.MailArchiveError):
        store.search()
