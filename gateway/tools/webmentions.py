"""Webmentions on the owner's site, through webmention-server (webmention.awfulwoman.com).

Other sites send replies, likes and reposts; the owner reviews them before they show. These tools
let the owner do that review from a chat: see what is waiting, approve or reject, and send
Webmentions for a post by hand. The server's admin token can do more (rules, deleting records);
these tools only expose the review and the send, so an agent cannot trust or block a whole site or
erase a record. Approving is a public act (it shows on the site), so only do it when the owner
has said which mentions to approve.
"""
from __future__ import annotations

import json

import httpx

from gateway.config import WebmentionsConfig

_config: WebmentionsConfig | None = None
_transport: httpx.BaseTransport | None = None

STATUSES = ("pending", "approved", "rejected", "deleted", "queued", "failed")
TYPES = ("reply", "like", "repost", "bookmark", "quote", "rsvp", "mention")
_TEXT = 400


def init(config: WebmentionsConfig, transport: httpx.BaseTransport | None = None) -> None:
    global _config, _transport
    _config = config
    _transport = transport


def _cfg() -> WebmentionsConfig:
    assert _config and _config.base_url and _config.token, (
        "webmentions not configured — set GATEWAY_WEBMENTIONS__BASE_URL and GATEWAY_WEBMENTIONS__TOKEN"
    )
    return _config


def _client() -> httpx.Client:
    cfg = _cfg()
    return httpx.Client(
        base_url=cfg.base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {cfg.token}"},
        timeout=30,
        transport=_transport,
    )


def _error(r: httpx.Response) -> str:
    try:
        message = r.json().get("error") or r.text
    except ValueError:
        message = r.text
    return json.dumps({"error": f"webmention-server returned {r.status_code}: {message}"})


def _summary(item: dict) -> dict:
    text = (item.get("content_text") or "").strip()
    return {
        "id": item["id"],
        "type": item.get("type"),
        "status": item["status"],
        "reason": item.get("reason"),
        "author": item.get("author_name"),
        "author_url": item.get("author_url"),
        "text": text if len(text) <= _TEXT else text[:_TEXT].rstrip() + "…",
        "on_page": item["target"],
        "from": item.get("url") or item["source"],
        "received": item["received_at"],
    }


def list_webmentions(status: str = "pending", type: str | None = None, page: str | None = None, limit: int = 20) -> str:
    """List Webmentions (replies, likes, reposts and mentions from other sites), newest first.

    status: pending (the default, waiting for review), approved, rejected, deleted, queued or failed.
    type: reply, like, repost, bookmark, quote, rsvp or mention. page: part of the page path they
    are about, e.g. "/notes/2026/10". Each has an id for moderate_webmention."""
    if status not in STATUSES:
        return json.dumps({"error": f"status is one of {', '.join(STATUSES)}"})
    if type is not None and type not in TYPES:
        return json.dumps({"error": f"type is one of {', '.join(TYPES)}"})
    params: dict = {"status": status, "limit": limit}
    if type:
        params["type"] = type
    if page:
        params["target"] = page
    with _client() as c:
        r = c.get("/admin/api/mentions", params=params)
        if r.status_code != 200:
            return _error(r)
        return json.dumps([_summary(i) for i in r.json()["items"]])


def moderate_webmention(id: str, status: str) -> str:
    """Approve or reject one Webmention. status is "approved" (it then shows on the page, with a copy of
    the author's photo) or "rejected" (it never shows; a repeat from the same page stays rejected).

    Approving publishes someone else's words under the owner's name, so do it only for mentions the
    owner has looked at and said yes to. This cannot trust or block a whole site."""
    if status not in ("approved", "rejected"):
        return json.dumps({"error": 'status is "approved" or "rejected"'})
    with _client() as c:
        r = c.post(f"/admin/api/mentions/{id}", json={"status": status})
        if r.status_code != 200:
            return _error(r)
        return json.dumps(r.json())


def send_webmentions(url: str) -> str:
    """Send Webmentions for one post on the owner's site now, even if it has not changed: every
    page it links to is told. url is the post's address on the site. Sending has to be turned on
    in the server; the answer says when it is not."""
    with _client() as c:
        r = c.post("/admin/api/send", json={"source": url})
        if r.status_code != 202:
            return _error(r)
        return json.dumps(r.json())


def register(mcp) -> None:
    for fn in [list_webmentions, moderate_webmention, send_webmentions]:
        mcp.tool()(fn)
