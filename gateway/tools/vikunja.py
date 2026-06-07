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


def _task_summary(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "title": t.get("title", ""),
        "description": t.get("description", ""),
        "done": t.get("done", False),
        "due_date": t.get("due_date"),
        "priority": t.get("priority", 0),
        "project_id": t.get("project_id"),
        "labels": [{"id": l.get("id"), "title": l.get("title")} for l in t.get("labels", [])],
        "reminders": t.get("reminders", []),
        "related_tasks": t.get("related_tasks", {}),
    }


def list_tasks(
    project_id: int = 0,
    filter_by: str = "",
    sort_by: str = "id",
    order_by: str = "asc",
    page: int = 1,
) -> str:
    """List Vikunja tasks. project_id filters to a specific project. filter_by accepts Vikunja filter syntax e.g. 'done=false'. sort_by can be id, title, due_date, priority, created, updated. order_by is asc or desc."""
    params: dict = {"sort_by": sort_by, "order_by": order_by, "page": page}
    if project_id and filter_by:
        params["filter"] = f"project_id={project_id} && {filter_by}"
    elif project_id:
        params["filter"] = f"project_id={project_id}"
    elif filter_by:
        params["filter"] = filter_by
    with _client() as c:
        r = c.get("/tasks", params=params)
        r.raise_for_status()
    return json.dumps([_task_summary(t) for t in r.json()])


def get_task(task_id: int) -> str:
    """Get a Vikunja task by ID. Returns full detail including labels, reminders, and related tasks."""
    with _client() as c:
        r = c.get(f"/tasks/{task_id}")
        r.raise_for_status()
    return json.dumps(_task_summary(r.json()))


def create_task(
    project_id: int,
    title: str,
    description: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Create a new Vikunja task in the given project. due_date is ISO 8601 (e.g. 2024-12-31T10:00:00Z). priority is 0 (none) through 5 (critical)."""
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
    return json.dumps(_task_summary(r.json()))


def update_task(
    task_id: int,
    title: str = "",
    description: str = "",
    done: str = "",
    due_date: str = "",
    priority: str = "",
) -> str:
    """Update a Vikunja task. Only supplied (non-empty) fields are changed. done must be 'true' or 'false'. priority is 0-5."""
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
        r = c.post(f"/tasks/{task_id}", json=body)
        r.raise_for_status()
    return json.dumps(_task_summary(r.json()))


def delete_task(task_id: int) -> str:
    """Delete a Vikunja task by ID."""
    with _client() as c:
        r = c.delete(f"/tasks/{task_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "task_id": task_id})


def list_labels() -> str:
    """List all Vikunja labels accessible to the configured token."""
    with _client() as c:
        r = c.get("/labels")
        r.raise_for_status()
    labels = [{"id": l.get("id"), "title": l.get("title"), "hex_color": l.get("hex_color", "")} for l in r.json()]
    return json.dumps(labels)


def add_task_label(task_id: int, label_id: int) -> str:
    """Attach a label to a Vikunja task. Use list_labels to find label IDs."""
    with _client() as c:
        r = c.put(f"/tasks/{task_id}/labels", json={"label_id": label_id})
        r.raise_for_status()
    return json.dumps({"status": "added", "task_id": task_id, "label_id": label_id})


def remove_task_label(task_id: int, label_id: int) -> str:
    """Remove a label from a Vikunja task."""
    with _client() as c:
        r = c.delete(f"/tasks/{task_id}/labels/{label_id}")
        r.raise_for_status()
    return json.dumps({"status": "removed", "task_id": task_id, "label_id": label_id})


def register(mcp) -> None:
    for fn in [
        list_projects,
        get_project,
        create_project,
        list_tasks,
        get_task,
        create_task,
        update_task,
        delete_task,
        list_labels,
        add_task_label,
        remove_task_label,
    ]:
        mcp.tool()(fn)
