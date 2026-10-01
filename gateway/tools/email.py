from __future__ import annotations
import json
from gateway.config import MailArchiveServerConfig
from gateway.mail_archive_server import store

_config: MailArchiveServerConfig | None = None


def init(config: MailArchiveServerConfig) -> None:
    global _config
    _config = config
    store.init(config)


def _account_filter(account: str) -> list[str] | None:
    """An explicit `account` argument always wins. Otherwise fall back to
    config's own ergonomic allowlist (empty = every account the bearer token
    can see server-side -- never a security boundary, spec §0)."""
    if account:
        return [account]
    return _config.accounts or None


def search_emails(
    query: str = "",
    account: str = "",
    sender: str = "",
    subject: str = "",
    since: str = "",
    until: str = "",
    order: str = "date_desc",
    cursor: str = "",
    limit: int = 20,
) -> str:
    """Search emails via the mail archive (a periodically-synced copy, not
    live — check unread state separately with fetch_unread_emails, since
    this may lag; `stale_seconds` in the response says by how much).
    account="" (default) searches every account in scope. since/until are
    ISO dates or datetimes, inclusive. order is "date_desc" (default) or
    "date_asc". Returns `next_cursor`: pass it back as `cursor` to continue
    the same walk from where this page left off; null once exhausted.
    """
    result = store.search(
        account=_account_filter(account), q=query or None, from_=sender or None,
        subject=subject or None, since=since or None, until=until or None,
        order=order, cursor=cursor or None, limit=limit,
    )
    return json.dumps({
        "messages": result["messages"],
        "total": result["total"],
        "next_cursor": result.get("next_cursor"),
        "stale_seconds": result["index"]["stale_seconds"],
    })


def list_emails(
    account: str = "",
    since: str = "",
    until: str = "",
    order: str = "date_desc",
    cursor: str = "",
    limit: int = 20,
) -> str:
    """List emails in date order, no search query — see search_emails for
    what each parameter means."""
    return search_emails(account=account, since=since, until=until, order=order, cursor=cursor, limit=limit)


def fetch_email_body(id: str) -> str:
    """Fetch the complete body of an email by its mail-archive-server `id`
    (from search_emails/list_emails's "id" field — NOT a Message-ID header;
    the archive's id is globally unique across every account, a Message-ID
    is not)."""
    msg = store.get_message(id)
    if msg is None:
        return json.dumps({"error": f"No email found with id: {id}"})
    return json.dumps(msg)


def mark_email_read(id: str) -> str:
    """Mark an email as read by its mail-archive-server `id`. Local to the
    archive only, for now (mail-archive-server#3): it updates the archive's
    own record immediately, shown here as "seen": true, but does not yet
    reach the real mailbox over IMAP — `upstream_synced` is always false
    until that lands. A phone or webmail checking the real account will
    still show it unread."""
    result = store.mark_read(id)
    if result is None:
        return json.dumps({"error": f"No email found with id: {id}"})
    return json.dumps(result)


def fetch_unread_emails(limit: int = 10) -> str:
    """Fetch unread emails across every account in scope. Triggers an
    account-scoped sync first so this reflects current state, not whatever
    the last periodic sync saw — a sync failing for one account is reported
    in `errors` without blocking the others. One combined mail-archive-server
    search afterwards does the cross-account merge/sort/limit, since the
    archive already does that correctly server-side."""
    target_accounts = _config.accounts or [a["name"] for a in store.accounts()]
    errors = []
    for acct in target_accounts:
        try:
            store.sync(account=acct)
        except store.MailArchiveError as exc:
            errors.append({"account": acct, "message": str(exc)})

    result = store.search(account=target_accounts or None, seen=False, order="date_desc", limit=limit)
    return json.dumps({"messages": result["messages"], "total": result["total"], "errors": errors})


def list_email_accounts() -> str:
    """List every mail account the bearer token can see, with its message
    count and sync health."""
    return json.dumps(store.accounts())


def register(mcp) -> None:
    for fn in [
        search_emails,
        list_emails,
        fetch_email_body,
        mark_email_read,
        fetch_unread_emails,
        list_email_accounts,
    ]:
        mcp.tool()(fn)
