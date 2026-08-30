"""Issues, backed by GitHub issues in a single repo (default awfulwoman/meta),
reached through the GitHub REST API.

GitHub issues natively carry a title, a markdown body, labels, comments and an
open/closed state. The gateway issue model has a few fields with no GitHub
equivalent — `status: in-progress`, `priority`, `due`, `project`, `related`,
`reminders` — so those are stored in a machine-readable block at the end of the
body:

    <description prose>

    ## Checklist

    - [ ] a task
    - [x] a done task

    <!-- gateway:issue
    priority: 2
    due: '2026-09-10'
    -->

The HTML comment renders as nothing on GitHub. `status` maps to GitHub state
(open/closed) plus, for `in-progress`, a `status` key in that block.

`project` is a vault-relative path (e.g. `Software/Podderton`) linking the issue
to an Obsidian project. It lives in the metadata block, and the tool also mirrors
it to a visible `project: <slug>` label (last path segment, slugified) so the
link shows in the GitHub UI and can be filtered on. That label is fully
tool-managed — created in the repo on demand, kept in sync with `project`, and
stripped from the `labels` field the tools return.
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
import httpx
import yaml
from gateway.config import GitHubConfig

_config: GitHubConfig | None = None
_API = "https://api.github.com"

_META_RE = re.compile(r"\n*<!-- gateway:issue\n(.*?)\n-->\s*$", re.DOTALL)
_CHECKLIST_HEADING = "## Checklist"
_META_KEYS = ("status", "priority", "due", "project", "related", "reminders")
_PROJECT_LABEL_PREFIX = "project: "


def init(config: GitHubConfig) -> None:
    global _config
    _config = config


def _cfg() -> GitHubConfig:
    assert _config and _config.repo and _config.token, (
        "issues not configured — set GATEWAY_GITHUB__REPO and GATEWAY_GITHUB__TOKEN"
    )
    return _config


def _client() -> httpx.Client:
    cfg = _cfg()
    return httpx.Client(
        base_url=_API,
        headers={
            "Authorization": f"Bearer {cfg.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )


def _repo_path() -> str:
    return f"/repos/{_cfg().repo}"


class _GitHubError(Exception):
    pass


def _check(resp: httpx.Response) -> Any:
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("message") or resp.text
        except Exception:
            msg = resp.text or f"HTTP {resp.status_code}"
        raise _GitHubError(msg)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def _next_link(link_header: str) -> str | None:
    for url, rel in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', link_header or ""):
        if rel == "next":
            return url
    return None


def _get_paginated(client: httpx.Client, path: str, params: dict | None = None) -> list:
    resp = client.get(path, params={**(params or {}), "per_page": 100})
    out: list = []
    while True:
        data = _check(resp)
        if isinstance(data, list):
            out.extend(data)
        nxt = _next_link(resp.headers.get("link", ""))
        if not nxt:
            return out
        resp = client.get(nxt)


def _graphql(client: httpx.Client, query: str, variables: dict) -> dict:
    data = _check(client.post("/graphql", json={"query": query, "variables": variables})) or {}
    if data.get("errors"):
        raise _GitHubError(data["errors"][0].get("message", "GraphQL error"))
    return data.get("data") or {}


# --- body <-> fields --------------------------------------------------------

def _split_meta(body: str) -> tuple[str, dict]:
    """Pull the gateway:issue block off the end of a body. Returns (body_without_meta, meta)."""
    body = body.replace("\r\n", "\n")
    m = _META_RE.search(body)
    if not m:
        return body.strip(), {}
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return body[: m.start()].strip(), meta


def _split_checklist(text: str) -> tuple[str, list[dict]]:
    """Split a meta-free body into (description, checklist)."""
    idx = text.find(_CHECKLIST_HEADING)
    if idx == -1:
        return text.strip(), []
    description = text[:idx].strip()
    checklist: list[dict] = []
    for line in text[idx + len(_CHECKLIST_HEADING):].splitlines():
        s = line.strip()
        if s.startswith("## "):
            break
        if s[:6].lower() == "- [x] ":
            checklist.append({"text": s[6:].strip(), "done": True})
        elif s.startswith("- [ ] "):
            checklist.append({"text": s[6:].strip(), "done": False})
    return description, checklist


def _parse_body(body: str) -> tuple[str, list[dict], dict]:
    """Returns (description, checklist, meta)."""
    text, meta = _split_meta(body or "")
    description, checklist = _split_checklist(text)
    return description, checklist, meta


def _render_body(description: str, checklist: list[dict], meta: dict) -> str:
    parts: list[str] = []
    if description.strip():
        parts.append(description.strip())
    if checklist:
        lines = [_CHECKLIST_HEADING, ""]
        lines += [f"- [{'x' if c.get('done') else ' '}] {c['text']}" for c in checklist]
        parts.append("\n".join(lines))
    clean = {k: meta[k] for k in _META_KEYS if meta.get(k) not in (None, "", [], 0)}
    if clean:
        parts.append("<!-- gateway:issue\n" + yaml.dump(clean, default_flow_style=False, allow_unicode=True, sort_keys=True).strip() + "\n-->")
    return "\n\n".join(parts).strip() + "\n"


def _status_of(gh_state: str, meta: dict) -> str:
    if str(gh_state).upper() == "CLOSED":
        return "done"
    return "in-progress" if meta.get("status") == "in-progress" else "open"


def _labels_of(gh_labels: list) -> list[str]:
    return [l["name"] for l in (gh_labels or [])]


def _visible_labels(gh_labels: list) -> list[str]:
    """Labels minus the tool-managed `project: <slug>` one (surfaced via `project`)."""
    return [n for n in _labels_of(gh_labels) if not n.startswith(_PROJECT_LABEL_PREFIX)]


def _project_slug(project: str) -> str:
    """Last path segment of a vault-relative project path, slugified."""
    seg = project.rstrip("/").split("/")[-1]
    return re.sub(r"[^a-z0-9]+", "-", seg.lower()).strip("-") or "project"


def _project_label(project: str) -> str:
    return f"{_PROJECT_LABEL_PREFIX}{_project_slug(project)}"


def _ensure_label(client: httpx.Client, name: str, description: str = "") -> None:
    """Create the label in the repo if it isn't there yet. Idempotent."""
    resp = client.get(f"{_repo_path()}/labels/{quote(name, safe='')}")
    if resp.status_code == 200:
        return
    if resp.status_code != 404:
        _check(resp)
    body: dict[str, str] = {"name": name, "color": "ededed"}
    if description:
        body["description"] = description
    resp = client.post(f"{_repo_path()}/labels", json=body)
    if resp.status_code not in (201, 422):  # 422: a concurrent request already made it
        _check(resp)


def _sync_project_label(client: httpx.Client, labels: list[str], project: str) -> list[str]:
    """Return `labels` with the tool-managed `project: <slug>` label reconciled to
    `project`: dropped when `project` is empty, otherwise created in the repo if
    missing and appended."""
    kept = [l for l in labels if not l.startswith(_PROJECT_LABEL_PREFIX)]
    if project:
        name = _project_label(project)
        _ensure_label(client, name, f"Linked to Obsidian project {project}")
        kept.append(name)
    return kept


def _summary(node: dict) -> dict:
    description, checklist, meta = _parse_body(node.get("body") or "")
    return {
        "id": node["number"],
        "title": node.get("title", ""),
        "project": meta.get("project", ""),
        "status": _status_of(node.get("state", "open"), meta),
        "priority": meta.get("priority", 0),
        "due": meta.get("due", ""),
        "labels": _visible_labels(node.get("labels")),
    }


# --- tools ----------------------------------------------------------------

def list_issues(
    project: str = "",
    status: str = "",
    priority: int = -1,
    label: str = "",
) -> str:
    """List issues in the GitHub issues repo. Filter by project (matched against the gateway metadata block), status (open/in-progress/done), priority (0-5, -1=all), or GitHub label."""
    params: dict[str, Any] = {
        "state": {"done": "closed", "open": "open", "in-progress": "open"}.get(status, "all"),
    }
    if label:
        params["labels"] = label
    try:
        with _client() as client:
            nodes = _get_paginated(client, f"{_repo_path()}/issues", params)
    except _GitHubError as e:
        return json.dumps({"error": str(e)})

    results = []
    for node in nodes:
        if "pull_request" in node:
            continue
        row = _summary(node)
        if project and row["project"] != project:
            continue
        if status and row["status"] != status:
            continue
        if priority >= 0 and row["priority"] != priority:
            continue
        results.append(row)
    results.sort(key=lambda x: x["id"])
    return json.dumps(results)


def get_issue(issue_id: int) -> str:
    """Get a single issue by its GitHub issue number. Returns full detail including checklist and comments."""
    try:
        with _client() as client:
            node = _check(client.get(f"{_repo_path()}/issues/{issue_id}"))
            raw_comments = _get_paginated(client, f"{_repo_path()}/issues/{issue_id}/comments")
    except _GitHubError as e:
        return json.dumps({"error": str(e)})

    description, checklist, meta = _parse_body(node.get("body") or "")
    comments = [
        {
            "timestamp": (c.get("created_at") or "")[:16],
            "author": (c.get("user") or {}).get("login", ""),
            "text": (c.get("body") or "").strip(),
        }
        for c in raw_comments
    ]
    return json.dumps({
        "id": node["number"],
        "title": node.get("title", ""),
        "project": meta.get("project", ""),
        "status": _status_of(node.get("state", "open"), meta),
        "priority": meta.get("priority", 0),
        "due": meta.get("due", ""),
        "labels": _visible_labels(node.get("labels")),
        "reminders": meta.get("reminders") or [],
        "related": meta.get("related") or [],
        "description": description,
        "checklist": checklist,
        "comments": comments,
    })


def create_issue(
    title: str,
    project: str = "",
    description: str = "",
    due: str = "",
    priority: int = 0,
    labels: list[str] | None = None,
    reminders: list[str] | None = None,
    related: list[int] | None = None,
    checklist_items: list[str] | None = None,
) -> str:
    """Create a new GitHub issue. Returns the new issue number, title, and URL. `project` is a vault-relative Obsidian project path; it adds a `project: <slug>` label (auto-created). Other labels must already exist in the repo."""
    meta: dict[str, Any] = {}
    if project:
        meta["project"] = project
    if due:
        meta["due"] = due
    if priority:
        meta["priority"] = priority
    if reminders:
        meta["reminders"] = reminders
    if related:
        meta["related"] = related

    checklist = [{"text": item, "done": False} for item in (checklist_items or [])]
    payload: dict[str, Any] = {"title": title, "body": _render_body(description, checklist, meta)}

    try:
        with _client() as client:
            final_labels = _sync_project_label(client, list(labels or []), project)
            if final_labels:
                payload["labels"] = final_labels
            node = _check(client.post(f"{_repo_path()}/issues", json=payload))
    except _GitHubError as e:
        return json.dumps({"error": str(e)})

    return json.dumps({
        "id": node.get("number"),
        "title": node.get("title", title),
        "url": node.get("html_url", ""),
    })


def update_issue(
    issue_id: int,
    title: str = "",
    status: str = "",
    project: str = "",
    description: str = "",
    due: str = "",
    priority: int = -1,
    labels: list[str] | None = None,
    reminders: list[str] | None = None,
    related: list[int] | None = None,
) -> str:
    """Update an issue. Only non-empty/non-default arguments are applied. priority=-1 means unchanged. labels, when given, replaces the full label set; the tool-managed `project: <slug>` label always tracks `project` regardless."""
    if status and status not in {"open", "in-progress", "done"}:
        return json.dumps({"error": f"Invalid status: {status!r}. Must be one of: open, in-progress, done"})

    try:
        with _client() as client:
            node = _check(client.get(f"{_repo_path()}/issues/{issue_id}"))

            old_description, checklist, meta = _parse_body(node.get("body") or "")
            if project:
                meta["project"] = project
            if due:
                meta["due"] = due
            if priority >= 0:
                meta["priority"] = priority
            if reminders is not None:
                meta["reminders"] = reminders
            if related is not None:
                meta["related"] = related
            if status == "in-progress":
                meta["status"] = "in-progress"
            elif status in {"open", "done"}:
                meta.pop("status", None)

            new_description = description if description else old_description
            payload: dict[str, Any] = {"body": _render_body(new_description, checklist, meta)}
            if title:
                payload["title"] = title
            if status == "done":
                payload["state"] = "closed"
            elif status in {"open", "in-progress"}:
                payload["state"] = "open"
            effective_project = meta.get("project", "")
            if labels is not None or project:
                base = list(labels) if labels is not None else _labels_of(node.get("labels"))
                payload["labels"] = _sync_project_label(client, base, effective_project)

            _check(client.patch(f"{_repo_path()}/issues/{issue_id}", json=payload))
    except _GitHubError as e:
        return json.dumps({"error": str(e)})

    return json.dumps({"status": "updated", "id": issue_id})


def delete_issue(issue_id: int) -> str:
    """Delete an issue by its GitHub issue number. Needs a token with permission to delete issues on the repo."""
    try:
        with _client() as client:
            node = _check(client.get(f"{_repo_path()}/issues/{issue_id}"))
            node_id = node.get("node_id")
            if not node_id:
                raise _GitHubError("could not resolve issue node id")
            _graphql(
                client,
                "mutation($id: ID!) { deleteIssue(input: {issueId: $id}) { clientMutationId } }",
                {"id": node_id},
            )
    except _GitHubError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"status": "deleted", "id": issue_id})


def add_issue_comment(issue_id: int, comment: str) -> str:
    """Add a comment to an issue."""
    try:
        with _client() as client:
            node = _check(client.post(f"{_repo_path()}/issues/{issue_id}/comments", json={"body": comment}))
    except _GitHubError as e:
        return json.dumps({"error": str(e)})
    timestamp = (node.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))[:16]
    return json.dumps({"status": "added", "id": issue_id, "timestamp": timestamp})


def add_checklist_item(issue_id: int, item: str) -> str:
    """Append a new unchecked checklist item to an issue."""
    try:
        with _client() as client:
            node = _check(client.get(f"{_repo_path()}/issues/{issue_id}"))
            description, checklist, meta = _parse_body(node.get("body") or "")
            checklist.append({"text": item, "done": False})
            _check(client.patch(
                f"{_repo_path()}/issues/{issue_id}",
                json={"body": _render_body(description, checklist, meta)},
            ))
    except _GitHubError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"status": "added", "id": issue_id, "item": item})


def toggle_checklist_item(issue_id: int, item_text: str) -> str:
    """Flip done/undone for the checklist item whose text matches item_text exactly."""
    try:
        with _client() as client:
            node = _check(client.get(f"{_repo_path()}/issues/{issue_id}"))
            description, checklist, meta = _parse_body(node.get("body") or "")
            for c in checklist:
                if c["text"] == item_text:
                    c["done"] = not c["done"]
                    _check(client.patch(
                        f"{_repo_path()}/issues/{issue_id}",
                        json={"body": _render_body(description, checklist, meta)},
                    ))
                    return json.dumps({"status": "toggled", "id": issue_id, "item": item_text, "done": c["done"]})
    except _GitHubError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"Checklist item not found: {item_text}"})


def register(mcp) -> None:
    for fn in [
        list_issues,
        get_issue,
        create_issue,
        update_issue,
        delete_issue,
        add_issue_comment,
        add_checklist_item,
        toggle_checklist_item,
    ]:
        mcp.tool()(fn)
