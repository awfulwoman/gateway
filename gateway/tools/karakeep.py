from __future__ import annotations
import json
import httpx
from gateway.config import KarakeepConfig

_config: KarakeepConfig | None = None


def init(config: KarakeepConfig) -> None:
    global _config
    _config = config


def _client() -> httpx.Client:
    assert _config and _config.base_url and _config.api_key, "Karakeep not configured (GATEWAY_KARAKEEP__BASE_URL and GATEWAY_KARAKEEP__API_KEY required)"
    return httpx.Client(
        base_url=f"{_config.base_url.rstrip('/')}/api/v1",
        headers={
            "Authorization": f"Bearer {_config.api_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )


def _bookmark_summary(b: dict) -> dict:
    content = b.get("content", {})
    tags = [t.get("name", "") for t in b.get("tags", [])]
    return {
        "id": b.get("id"),
        "title": b.get("title") or content.get("title") or content.get("url", ""),
        "url": content.get("url") if content.get("type") == "link" else None,
        "type": content.get("type"),
        "tags": tags,
        "favourited": b.get("favourited"),
        "archived": b.get("archived"),
        "created_at": b.get("createdAt"),
        "note": b.get("note"),
        "summary": b.get("summary") or content.get("description", ""),
    }


def search_bookmarks(query: str, limit: int = 10, cursor: str = "") -> str:
    """Search bookmarks. Supports qualifiers: is:fav, is:archived, is:tagged, is:link, is:text, url:<value>, #<tag>, list:<name>, after:<date>, before:<date>."""
    params: dict = {"q": query, "limit": limit, "includeContent": "false"}
    if cursor:
        params["cursor"] = cursor
    with _client() as c:
        r = c.get("/bookmarks/search", params=params)
        r.raise_for_status()
        data = r.json()
    bookmarks = [_bookmark_summary(b) for b in data.get("bookmarks", [])]
    return json.dumps({"bookmarks": bookmarks, "next_cursor": data.get("nextCursor")})


def get_bookmark(bookmark_id: str) -> str:
    """Get a bookmark by ID. Returns full metadata including tags, note, and summary."""
    with _client() as c:
        r = c.get(f"/bookmarks/{bookmark_id}", params={"includeContent": "false"})
        r.raise_for_status()
    return json.dumps(_bookmark_summary(r.json()))


def get_bookmark_content(bookmark_id: str) -> str:
    """Get the full content of a bookmark (HTML converted to plain text for link bookmarks, raw text for text bookmarks)."""
    with _client() as c:
        r = c.get(f"/bookmarks/{bookmark_id}", params={"includeContent": "true"})
        r.raise_for_status()
        data = r.json()
    content = data.get("content", {})
    btype = content.get("type")
    if btype == "link":
        text = content.get("htmlContent", "")
        # Strip HTML tags naively so we don't need an extra dependency
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    elif btype == "text":
        text = content.get("text", "")
    else:
        text = content.get("content", "")
    return json.dumps({"id": bookmark_id, "type": btype, "content": text})


def create_bookmark(type: str, content: str, title: str = "") -> str:
    """Create a bookmark. type must be 'link' (content is a URL) or 'text' (content is freeform text). title is optional."""
    if type == "link":
        body: dict = {"type": "link", "url": content}
    elif type == "text":
        body = {"type": "text", "text": content}
    else:
        return json.dumps({"status": "error", "message": "type must be 'link' or 'text'"})
    if title:
        body["title"] = title
    with _client() as c:
        r = c.post("/bookmarks", json=body)
        r.raise_for_status()
    return json.dumps({"status": "created", "bookmark": _bookmark_summary(r.json())})


def update_bookmark(
    bookmark_id: str,
    title: str = "",
    note: str = "",
    archived: str = "",
    favourited: str = "",
) -> str:
    """Update a bookmark. Only supplied (non-empty) fields are changed. archived and favourited must be 'true' or 'false'."""
    body: dict = {}
    if title:
        body["title"] = title
    if note:
        body["note"] = note
    if archived in ("true", "false"):
        body["archived"] = archived == "true"
    if favourited in ("true", "false"):
        body["favourited"] = favourited == "true"
    if not body:
        return json.dumps({"status": "error", "message": "No fields to update"})
    with _client() as c:
        r = c.patch(f"/bookmarks/{bookmark_id}", json=body)
        r.raise_for_status()
    return json.dumps({"status": "updated", "bookmark": _bookmark_summary(r.json())})


def attach_tags(bookmark_id: str, tags: str) -> str:
    """Attach tags to a bookmark. tags is a comma-separated list of tag names."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    body = {"tags": [{"tagName": t} for t in tag_list]}
    with _client() as c:
        r = c.post(f"/bookmarks/{bookmark_id}/tags", json=body)
        r.raise_for_status()
    return json.dumps({"status": "tags_attached", "tags": tag_list})


def detach_tags(bookmark_id: str, tags: str) -> str:
    """Detach tags from a bookmark. tags is a comma-separated list of tag names."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    body = {"tags": [{"tagName": t} for t in tag_list]}
    with _client() as c:
        r = c.delete(f"/bookmarks/{bookmark_id}/tags", json=body)
        r.raise_for_status()
    return json.dumps({"status": "tags_detached", "tags": tag_list})


def list_tags() -> str:
    """List all tags in Karakeep."""
    with _client() as c:
        r = c.get("/tags")
        r.raise_for_status()
    tags = [{"id": t.get("id"), "name": t.get("name"), "count": t.get("numBookmarks")} for t in r.json().get("tags", [])]
    return json.dumps(tags)


def get_lists() -> str:
    """List all bookmark lists (collections)."""
    with _client() as c:
        r = c.get("/lists")
        r.raise_for_status()
    lists = [{"id": l.get("id"), "name": l.get("name"), "icon": l.get("icon"), "parent_id": l.get("parentId")} for l in r.json().get("lists", [])]
    return json.dumps(lists)


def create_list(name: str, icon: str, parent_id: str = "") -> str:
    """Create a new bookmark list. icon should be an emoji. parent_id is optional for nested lists."""
    body: dict = {"name": name, "icon": icon}
    if parent_id:
        body["parentId"] = parent_id
    with _client() as c:
        r = c.post("/lists", json=body)
        r.raise_for_status()
    data = r.json()
    return json.dumps({"status": "created", "id": data.get("id"), "name": data.get("name")})


def add_to_list(list_id: str, bookmark_id: str) -> str:
    """Add a bookmark to a list."""
    with _client() as c:
        r = c.put(f"/lists/{list_id}/bookmarks/{bookmark_id}")
        r.raise_for_status()
    return json.dumps({"status": "added", "list_id": list_id, "bookmark_id": bookmark_id})


def remove_from_list(list_id: str, bookmark_id: str) -> str:
    """Remove a bookmark from a list."""
    with _client() as c:
        r = c.delete(f"/lists/{list_id}/bookmarks/{bookmark_id}")
        r.raise_for_status()
    return json.dumps({"status": "removed", "list_id": list_id, "bookmark_id": bookmark_id})


def register(mcp) -> None:
    for fn in [
        search_bookmarks,
        get_bookmark,
        get_bookmark_content,
        create_bookmark,
        update_bookmark,
        attach_tags,
        detach_tags,
        list_tags,
        get_lists,
        create_list,
        add_to_list,
        remove_from_list,
    ]:
        mcp.tool()(fn)
