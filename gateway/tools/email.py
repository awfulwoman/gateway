from __future__ import annotations
import email as email_lib
import imaplib
import json
from contextlib import contextmanager
from gateway.config import IMAPConfig

_config: IMAPConfig | None = None


def init(config: IMAPConfig) -> None:
    global _config
    _config = config


@contextmanager
def _connection(folder: str = "INBOX"):
    assert _config is not None, "email.init() not called"
    conn = imaplib.IMAP4_SSL(_config.host, _config.port)
    conn.login(_config.username, _config.password)
    conn.select(folder)
    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _parse_headers(raw: bytes) -> dict:
    msg = email_lib.message_from_bytes(raw)
    return {
        "message_id": msg.get("Message-ID", "").strip(),
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
    }


def _parse_full(raw: bytes) -> dict:
    msg = email_lib.message_from_bytes(raw)
    body_plain = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_plain:
                body_plain = part.get_payload(decode=True).decode(errors="replace")
            elif ct == "text/html" and not body_html:
                body_html = part.get_payload(decode=True).decode(errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            if msg.get_content_type() == "text/html":
                body_html = payload.decode(errors="replace")
            else:
                body_plain = payload.decode(errors="replace")
    return {
        "message_id": msg.get("Message-ID", "").strip(),
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "body": body_plain or body_html,
    }


def _safe_query(s: str) -> str:
    return s.replace('"', "")


def list_folders() -> str:
    """List all available IMAP folders/mailboxes."""
    with _connection() as conn:
        _, data = conn.list()
    folders = []
    for item in (data or []):
        if item:
            parts = item.decode().split(' "/" ')
            if len(parts) >= 2:
                folders.append(parts[-1].strip().strip('"'))
    return json.dumps(folders)


def list_emails(folder: str = "INBOX", max_count: int = 20) -> str:
    """List the most recent emails in a folder (default INBOX). Returns headers only (no body). max_count defaults to 20."""
    with _connection(folder) as conn:
        _, data = conn.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-max_count:]
        results = []
        for uid in reversed(ids):
            _, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER])")
            if msg_data and msg_data[0]:
                results.append(_parse_headers(msg_data[0][1]))
    return json.dumps(results)


def fetch_unread_emails(max_count: int = 10) -> str:
    """Fetch unread emails from INBOX. Returns headers and a short body preview. max_count defaults to 10."""
    with _connection() as conn:
        _, data = conn.search(None, "UNSEEN")
        ids = data[0].split()[-max_count:]
        results = []
        for uid in ids:
            _, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
            if msg_data and msg_data[0]:
                parsed = _parse_full(msg_data[0][1])
                parsed["body_preview"] = parsed.pop("body", "")[:400]
                results.append(parsed)
    return json.dumps(results)


def search_emails(
    query: str,
    search_in: str = "all",
    folder: str = "INBOX",
    max_results: int = 20,
) -> str:
    """Search emails. search_in can be 'subject', 'from', 'body', or 'all' (default). Returns headers and body preview."""
    q = _safe_query(query)
    criteria_map = {
        "subject": f'SUBJECT "{q}"',
        "from": f'FROM "{q}"',
        "body": f'TEXT "{q}"',
        "all": f'(OR (OR SUBJECT "{q}" FROM "{q}") TEXT "{q}")',
    }
    criteria = criteria_map.get(search_in, criteria_map["all"])

    with _connection(folder) as conn:
        _, data = conn.search(None, criteria)
        ids = data[0].split()[-max_results:]
        results = []
        for uid in reversed(ids):
            _, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
            if msg_data and msg_data[0]:
                parsed = _parse_full(msg_data[0][1])
                parsed["body_preview"] = parsed.pop("body", "")[:400]
                results.append(parsed)
    return json.dumps(results)


def fetch_email_body(message_id: str) -> str:
    """Fetch the complete body of an email by its Message-ID header value (from list_emails or search_emails)."""
    q = _safe_query(message_id)
    with _connection() as conn:
        _, data = conn.search(None, f'HEADER Message-ID "{q}"')
        ids = data[0].split()
        if not ids:
            return json.dumps({"error": f"No email found with Message-ID: {message_id}"})
        _, msg_data = conn.fetch(ids[0], "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            return json.dumps({"error": "Failed to fetch message"})
        return json.dumps(_parse_full(msg_data[0][1]))


def mark_email_read(message_id: str) -> str:
    """Mark an email as read by its Message-ID."""
    q = _safe_query(message_id)
    with _connection() as conn:
        _, data = conn.search(None, f'HEADER Message-ID "{q}"')
        ids = data[0].split()
        if not ids:
            return json.dumps({"status": "not_found", "message": f"No email with Message-ID: {message_id}"})
        conn.store(ids[0], "+FLAGS", "\\Seen")
    return json.dumps({"status": "marked_read", "message_id": message_id})


def register(mcp) -> None:
    for fn in [
        list_folders,
        list_emails,
        fetch_unread_emails,
        search_emails,
        fetch_email_body,
        mark_email_read,
    ]:
        mcp.tool()(fn)
