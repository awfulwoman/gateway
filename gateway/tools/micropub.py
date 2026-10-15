"""Draft posts on the owner's site, through micropub-server (indie.awfulwoman.com).

The token this uses is issued with the `draft update media` scopes and no
`delete`: the server then forces every created post to be a draft and only
lets updates touch drafts. An agent prepares drafts; the owner publishes and
deletes in the server's web UI (the tools return its edit link).
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from gateway.config import MicropubConfig

_config: MicropubConfig | None = None
_transport: httpx.BaseTransport | None = None

# Post types the site defines (data/micropub.yaml). Anything else is a typo.
POST_TYPES = ("note", "article", "bookmark", "like", "reply", "repost", "quote", "photo", "checkin", "page")
_PAGES_CHANNEL = "pages"


def init(config: MicropubConfig, transport: httpx.BaseTransport | None = None) -> None:
    global _config, _transport
    _config = config
    _transport = transport


def _cfg() -> MicropubConfig:
    assert _config and _config.base_url and _config.token, (
        "micropub not configured — set GATEWAY_MICROPUB__BASE_URL and GATEWAY_MICROPUB__TOKEN"
    )
    return _config


def _client() -> httpx.Client:
    cfg = _cfg()
    return httpx.Client(
        base_url=cfg.base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {cfg.token}"},
        timeout=60,
        transport=_transport,
    )


def _error(r: httpx.Response) -> str:
    try:
        body = r.json()
        message = body.get("error_description") or body.get("error") or r.text
    except ValueError:
        message = r.text
    return json.dumps({"error": f"micropub-server returned {r.status_code}: {message}"})


def _mf2_value(key: str, value: Any) -> list:
    """One property as Micropub JSON wants it: always a list. A checkin is an h-card."""
    if key == "checkin" and isinstance(value, dict):
        card = {k: [str(v)] for k, v in value.items() if v not in (None, "")}
        return [{"type": ["h-card"], "properties": card}]
    return value if isinstance(value, list) else [value]


def _edit_link(c: httpx.Client, url: str) -> str | None:
    r = c.get("/micropub", params={"q": "source", "url": url, "properties": "uid"})
    if r.status_code != 200:
        return None
    uid = (r.json().get("properties", {}).get("uid") or [None])[0]
    return f"{str(c.base_url).rstrip('/')}/posts/{uid}/edit" if uid else None


def create_post(post_type: str, properties: dict) -> str:
    """Create a draft post on the owner's site. It is always a draft: the owner publishes it from the edit link.

    post_type: note, article, bookmark, like, reply, repost, quote, photo, checkin or page.
    properties: Micropub properties, e.g. {"name": "...", "content": "..."}. Link types take
    bookmark-of, like-of, in-reply-to, repost-of or quotation-of (a URL). photo takes photo (a URL
    from upload_media) and mp-photo-alt. checkin takes {"name": ..., "latitude": ..., "longitude": ...}.
    category is a list of tags. A page (served at /<slug>/, from its name) needs name and content.
    Returns the post's URL and the web UI link to edit and publish it."""
    if post_type not in POST_TYPES:
        return json.dumps({"error": f"Unknown post type {post_type!r}; use one of {', '.join(POST_TYPES)}"})
    props = dict(properties)
    if post_type == "page":
        props["mp-channel"] = _PAGES_CHANNEL
    body = {"type": ["h-entry"], "properties": {k: _mf2_value(k, v) for k, v in props.items()}}
    with _client() as c:
        r = c.post("/micropub", json=body)
        if r.status_code not in (201, 202):
            return _error(r)
        url = r.headers.get("location", "")
        return json.dumps({"url": url, "status": "draft", "edit_url": _edit_link(c, url)})


def update_post(url: str, replace: dict | None = None, add: dict | None = None, delete: list[str] | dict | None = None) -> str:
    """Change a draft: replace or add properties, or delete properties (a list of names, or {name: [values]}).

    Only drafts can be changed; a published post is edited by the owner. Properties are as in create_post."""
    body: dict = {"action": "update", "url": url}
    if replace:
        body["replace"] = {k: _mf2_value(k, v) for k, v in replace.items()}
    if add:
        body["add"] = {k: _mf2_value(k, v) for k, v in add.items()}
    if delete:
        body["delete"] = delete
    with _client() as c:
        r = c.post("/micropub", json=body)
        if r.status_code not in (200, 201, 202):
            return _error(r)
        return json.dumps({"url": r.headers.get("location", url), "edit_url": _edit_link(c, r.headers.get("location", url))})


def get_post(url: str) -> str:
    """Get one post's properties (Micropub JSON), by its URL."""
    with _client() as c:
        r = c.get("/micropub", params={"q": "source", "url": url})
        return json.dumps(r.json()) if r.status_code == 200 else _error(r)


def list_posts(post_type: str | None = None, status: str | None = None, limit: int = 20) -> str:
    """List posts, newest first. status is "draft" or "published" (default both); post_type as in create_post."""
    params: dict = {"q": "source", "limit": limit}
    if post_type:
        params["post-type"] = post_type
    if status:
        params["post-status"] = status
    with _client() as c:
        r = c.get("/micropub", params=params)
        if r.status_code != 200:
            return _error(r)
        return json.dumps([_summary(i) for i in r.json().get("items", [])])


def _summary(item: dict) -> dict:
    p = item.get("properties", {})
    first = lambda key: (p.get(key) or [None])[0]  # noqa: E731
    content = first("content")
    return {
        "url": first("url"),
        "type": first("post-type"),
        "status": first("post-status"),
        "name": first("name"),
        "published": first("published"),
        "content": content.get("value") if isinstance(content, dict) else content,
    }


def upload_media(path: str) -> str:
    """Upload an image from a local path to the site's media endpoint. Returns the URL to use as a post's photo.

    The path is on the machine the gateway runs on."""
    file = Path(path).expanduser()
    if not file.is_file():
        return json.dumps({"error": f"No such file: {path}"})
    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    with _client() as c:
        r = c.post("/media", files={"file": (file.name, file.read_bytes(), mime)})
        if r.status_code not in (201, 202):
            return _error(r)
        return json.dumps({"url": r.headers.get("location", "")})


def register(mcp) -> None:
    for fn in [create_post, update_post, get_post, list_posts, upload_media]:
        mcp.tool()(fn)
