from __future__ import annotations
import json
import httpx
from gateway.config import VikunjaConfig

_config: VikunjaConfig | None = None


def init(config: VikunjaConfig) -> None:
    global _config
    _config = config


def _client() -> httpx.Client:
    assert _config and _config.base_url and _config.api_token, (
        "Vikunja not configured (GATEWAY_VIKUNJA__BASE_URL and GATEWAY_VIKUNJA__API_TOKEN required)"
    )
    return httpx.Client(
        base_url=f"{_config.base_url.rstrip('/')}/api/v1",
        headers={
            "Authorization": f"Bearer {_config.api_token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )


def _project_summary(p: dict) -> dict:
    return {
        "id": p.get("id"),
        "title": p.get("title", ""),
        "description": p.get("description", ""),
        "is_archived": p.get("is_archived", False),
        "parent_project_id": p.get("parent_project_id"),
    }


def list_projects() -> str:
    """List all Vikunja projects accessible to the configured token."""
    with _client() as c:
        r = c.get("/projects")
        r.raise_for_status()
    return json.dumps([_project_summary(p) for p in r.json()])


def get_project(project_id: int) -> str:
    """Get a Vikunja project by ID."""
    with _client() as c:
        r = c.get(f"/projects/{project_id}")
        r.raise_for_status()
    return json.dumps(_project_summary(r.json()))


def create_project(title: str, description: str = "", parent_project_id: int = 0) -> str:
    """Create a new Vikunja project. parent_project_id is optional (0 = top-level)."""
    body: dict = {"title": title}
    if description:
        body["description"] = description
    if parent_project_id:
        body["parent_project_id"] = parent_project_id
    with _client() as c:
        r = c.put("/projects", json=body)
        r.raise_for_status()
    return json.dumps(_project_summary(r.json()))


def _issue_summary(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "title": t.get("title", ""),
        "description": t.get("description", ""),
        "done": t.get("done", False),
        "due_date": t.get("due_date"),
        "priority": t.get("priority", 0),
        "project_id": t.get("project_id"),
        "labels": [{"id": l.get("id"), "title": l.get("title")} for l in (t.get("labels") or [])],
        "reminders": t.get("reminders") or [],
        "related_tasks": t.get("related_tasks") or {},
    }


def list_issues(
    project_id: int = 0,
    filter_by: str = "",
    sort_by: str = "id",
    order_by: str = "asc",
    page: int = 1,
) -> str:
    """List Vikunja issues. project_id filters to a specific project. filter_by accepts Vikunja filter syntax e.g. 'done=false'. sort_by can be id, title, due_date, priority, created, updated. order_by is asc or desc."""
    params: dict = {"sort_by": sort_by, "order_by": order_by, "page": page}
    if project_id and filter_by:
        params["filter"] = f"project = {project_id} && {filter_by}"
    elif project_id:
        params["filter"] = f"project = {project_id}"
    elif filter_by:
        params["filter"] = filter_by
    with _client() as c:
        r = c.get("/tasks", params=params)
        r.raise_for_status()
    return json.dumps([_issue_summary(t) for t in r.json()])


def get_issue(issue_id: int) -> str:
    """Get a Vikunja issue by ID. Returns full detail including labels, reminders, and related issues."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))


def _find_inbox_project_id() -> int:
    with _client() as c:
        r = c.get("/projects")
        r.raise_for_status()
    for p in r.json():
        if (p.get("title") or "").strip().lower() == "inbox":
            return int(p["id"])
    raise ValueError("No project titled 'Inbox' found")


def create_issue(
    project_id: int = 0,
    title: str = "",
    description: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Create a new Vikunja issue. If project_id is 0 (or omitted), the issue is created in the user's Inbox project. due_date is ISO 8601 (e.g. 2024-12-31T10:00:00Z). priority is 0 (none) through 5 (critical)."""
    if not project_id:
        project_id = _find_inbox_project_id()
    body: dict = {"title": title}
    if description:
        body["description"] = description
    if due_date:
        body["due_date"] = due_date
    if priority:
        body["priority"] = int(priority)
    with _client() as c:
        r = c.put(f"/projects/{project_id}/tasks", json=body)
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))


def update_issue(
    issue_id: int,
    title: str = "",
    description: str = "",
    done: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Update a Vikunja issue. Only supplied (non-empty) fields are changed. done must be 'true' or 'false'. priority is 0-5."""
    body: dict = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if done in ("true", "false"):
        body["done"] = done == "true"
    if due_date:
        body["due_date"] = due_date
    if priority:
        body["priority"] = int(priority)
    if not body:
        return json.dumps({"status": "error", "message": "No fields to update"})
    with _client() as c:
        r = c.post(f"/tasks/{issue_id}", json=body)
        r.raise_for_status()
    return json.dumps(_issue_summary(r.json()))


def delete_issue(issue_id: int) -> str:
    """Delete a Vikunja issue by ID."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "issue_id": issue_id})


def list_labels() -> str:
    """List all Vikunja labels accessible to the configured token."""
    with _client() as c:
        r = c.get("/labels")
        r.raise_for_status()
    labels = [{"id": l.get("id"), "title": l.get("title"), "hex_color": l.get("hex_color", "")} for l in r.json()]
    return json.dumps(labels)


def add_issue_label(issue_id: int, label_id: int) -> str:
    """Attach a label to a Vikunja issue. Use list_labels to find label IDs."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/labels", json={"label_id": label_id})
        r.raise_for_status()
    return json.dumps({"status": "added", "issue_id": issue_id, "label_id": label_id})


def remove_issue_label(issue_id: int, label_id: int) -> str:
    """Remove a label from a Vikunja issue."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}/labels/{label_id}")
        r.raise_for_status()
    return json.dumps({"status": "removed", "issue_id": issue_id, "label_id": label_id})


def list_issue_comments(issue_id: int) -> str:
    """Get all comments on a Vikunja issue."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}/comments")
        r.raise_for_status()
    comments = [
        {
            "id": item.get("id"),
            "comment": item.get("comment", ""),
            "created": item.get("created"),
            "author": item.get("author", {}).get("username", ""),
        }
        for item in r.json()
    ]
    return json.dumps(comments)


def add_issue_comment(issue_id: int, comment: str) -> str:
    """Add a comment to a Vikunja issue."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/comments", json={"comment": comment})
        r.raise_for_status()
    data = r.json()
    return json.dumps({
        "id": data.get("id"),
        "comment": data.get("comment", ""),
        "created": data.get("created"),
    })


def list_issue_relations(issue_id: int) -> str:
    """Get all relations for a Vikunja issue. Returns a dict keyed by relation kind (e.g. 'subtask', 'blocking')."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("related_tasks", {}))


def add_issue_relation(issue_id: int, other_issue_id: int, relation_kind: str) -> str:
    """Create a relation between two Vikunja issues. relation_kind: subtask, parenttask, related, duplicateof, duplicates, blocking, blocked, precedes, follows, copiedfrom, copiedto."""
    with _client() as c:
        r = c.put(f"/tasks/{issue_id}/relations", json={"other_task_id": other_issue_id, "relation_kind": relation_kind})
        r.raise_for_status()
    return json.dumps({"status": "created", "issue_id": issue_id, "other_issue_id": other_issue_id, "relation_kind": relation_kind})


def delete_issue_relation(issue_id: int, relation_kind: str, other_issue_id: int) -> str:
    """Remove a relation between two Vikunja issues. relation_kind and other_issue_id must match an existing relation."""
    with _client() as c:
        r = c.delete(f"/tasks/{issue_id}/relations/{relation_kind}/{other_issue_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "issue_id": issue_id, "relation_kind": relation_kind, "other_issue_id": other_issue_id})


def list_issue_reminders(issue_id: int) -> str:
    """Get all reminders for a Vikunja issue. Each reminder has a 'reminder' field (ISO 8601 datetime)."""
    with _client() as c:
        r = c.get(f"/tasks/{issue_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("reminders", []))


def set_issue_reminders(issue_id: int, reminders_json: str) -> str:
    """Replace all reminders on a Vikunja issue. reminders_json is a JSON array of reminder objects, e.g. '[{"reminder": "2024-12-01T09:00:00Z"}]'. Pass '[]' to clear all reminders. Call list_issue_reminders first to see existing reminders before modifying."""
    reminders = json.loads(reminders_json)
    with _client() as c:
        r = c.post(f"/tasks/{issue_id}", json={"reminders": reminders})
        r.raise_for_status()
    return json.dumps({"status": "updated", "issue_id": issue_id, "reminders": r.json().get("reminders", [])})


def register(mcp) -> None:
    for fn in [
        list_projects,
        get_project,
        create_project,
        list_issues,
        get_issue,
        create_issue,
        update_issue,
        delete_issue,
        list_labels,
        add_issue_label,
        remove_issue_label,
        list_issue_comments,
        add_issue_comment,
        list_issue_relations,
        add_issue_relation,
        delete_issue_relation,
        list_issue_reminders,
        set_issue_reminders,
    ]:
        mcp.tool()(fn)
