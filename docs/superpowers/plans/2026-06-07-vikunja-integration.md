# Vikunja Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `vikunja.py` tool module exposing 18 MCP tools for Vikunja task and project management.

**Architecture:** Single `gateway/tools/vikunja.py` module following the existing `init()`/`_client()`/`register()` pattern from `karakeep.py`. Config added to `config.py` via a `VikunjaConfig` model loaded from env vars. Wired into `main.py` alongside existing tools.

**Tech Stack:** Python 3.12, httpx, FastMCP, pydantic-settings, pytest + unittest.mock

---

## API reference (used throughout tasks below)

Base URL: `{GATEWAY_VIKUNJA__BASE_URL}/api/v1`
Auth header: `Authorization: Bearer {GATEWAY_VIKUNJA__API_TOKEN}`

Key endpoints:
- `GET /projects` — list all projects
- `GET /projects/{id}` — get one project
- `PUT /projects` — create project (body: `title`, `description`, `parent_project_id`)
- `GET /tasks` — list tasks (params: `filter`, `sort_by`, `order_by`, `page`, `per_page`)
- `GET /tasks/{id}` — get one task
- `PUT /projects/{id}/tasks` — create task (body: task fields)
- `POST /tasks/{id}` — update task (partial, only non-null sent)
- `DELETE /tasks/{id}` — delete task
- `GET /labels` — list labels
- `PUT /tasks/{task}/labels` — add label (body: `{"label_id": <int>}`)
- `DELETE /tasks/{task}/labels/{label}` — remove label
- `GET /tasks/{taskID}/comments` — list comments
- `PUT /tasks/{taskID}/comments` — add comment (body: `{"comment": "<text>"}`)
- `PUT /tasks/{taskID}/relations` — add relation (body: `{"other_task_id": <int>, "relation_kind": "<kind>"}`)
- `DELETE /tasks/{taskID}/relations/{relationKind}/{otherTaskID}` — delete relation
- Reminders: embedded in task model (`reminders` array); manage via `POST /tasks/{id}` with `{"reminders": [...]}`

Valid `relation_kind` values: `subtask`, `parenttask`, `related`, `duplicateof`, `duplicates`, `blocking`, `blocked`, `precedes`, `follows`, `copiedfrom`, `copiedto`

---

## File map

| Action | Path |
|--------|------|
| Modify | `gateway/config.py` |
| Modify | `.env.example` |
| Create | `gateway/tools/vikunja.py` |
| Modify | `gateway/main.py` |
| Create | `tests/test_vikunja.py` |

---

## Task 1: Add VikunjaConfig

**Files:**
- Modify: `gateway/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing test**

Create `tests/test_vikunja.py`:

```python
from gateway.config import Config


def test_vikunja_config_defaults():
    c = Config()
    assert c.vikunja.base_url == ""
    assert c.vikunja.api_token == ""


def test_vikunja_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_VIKUNJA__BASE_URL", "https://vikunja.example.com")
    monkeypatch.setenv("GATEWAY_VIKUNJA__API_TOKEN", "tok-abc123")
    c = Config()
    assert c.vikunja.base_url == "https://vikunja.example.com"
    assert c.vikunja.api_token == "tok-abc123"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/charlie/Code/awfulwoman/gateway && uv run pytest tests/test_vikunja.py::test_vikunja_config_defaults -v
```

Expected: `AttributeError: 'Config' object has no attribute 'vikunja'`

- [ ] **Step 3: Add VikunjaConfig to config.py**

In `gateway/config.py`, add after `OwnTracksConfig`:

```python
class VikunjaConfig(BaseModel):
    base_url: str = ""
    api_token: str = ""
```

And in the `Config` class, add:

```python
vikunja: VikunjaConfig = VikunjaConfig()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_vikunja_config_defaults tests/test_vikunja.py::test_vikunja_config_from_env -v
```

Expected: 2 passed

- [ ] **Step 5: Update .env.example**

Add to the end of `.env.example`:

```
# Vikunja task management
GATEWAY_VIKUNJA__BASE_URL=https://vikunja.example.com
GATEWAY_VIKUNJA__API_TOKEN=your-api-token
```

- [ ] **Step 6: Commit**

```bash
git add gateway/config.py .env.example tests/test_vikunja.py
git commit -m "feat: add VikunjaConfig to gateway config"
```

---

## Task 2: Create vikunja.py skeleton

**Files:**
- Create: `gateway/tools/vikunja.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_vikunja.py`:

```python
import json
from unittest.mock import MagicMock, patch
from gateway.config import VikunjaConfig
import gateway.tools.vikunja as vikunja


def _make_mock_client():
    """Returns (mock_client_fn, mock_client) ready for use with patch."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


def test_client_raises_when_not_configured():
    vikunja.init(VikunjaConfig(base_url="", api_token=""))
    import pytest
    with pytest.raises(AssertionError):
        vikunja._client()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_vikunja.py::test_client_raises_when_not_configured -v
```

Expected: `ModuleNotFoundError` or `ImportError` — file doesn't exist yet

- [ ] **Step 3: Create gateway/tools/vikunja.py**

```python
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


def register(mcp) -> None:
    for fn in []:
        mcp.tool()(fn)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_vikunja.py::test_client_raises_when_not_configured -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add vikunja.py skeleton with init/_client"
```

---

## Task 3: Project tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_projects():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0},
        {"id": 2, "title": "Work", "description": "Work tasks", "is_archived": False, "parent_project_id": 0},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_projects())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "Inbox"


def test_get_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_project(1))
    assert result["id"] == 1
    mock_client.get.assert_called_once_with("/projects/1")


def test_create_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 3, "title": "New Project", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("New Project"))
    assert result["id"] == 3
    assert result["title"] == "New Project"
    mock_client.put.assert_called_once_with("/projects", json={"title": "New Project"})


def test_create_project_with_parent():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 4, "title": "Sub", "description": "desc", "is_archived": False, "parent_project_id": 1
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("Sub", description="desc", parent_project_id=1))
    assert result["parent_project_id"] == 1
    mock_client.put.assert_called_once_with(
        "/projects", json={"title": "Sub", "description": "desc", "parent_project_id": 1}
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_projects tests/test_vikunja.py::test_get_project tests/test_vikunja.py::test_create_project -v
```

Expected: `AttributeError: module 'gateway.tools.vikunja' has no attribute 'list_projects'`

- [ ] **Step 3: Implement project tools in vikunja.py**

Add these functions before `register()`:

```python
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
```

Update `register()` to include the new functions:

```python
def register(mcp) -> None:
    for fn in [
        list_projects,
        get_project,
        create_project,
    ]:
        mcp.tool()(fn)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_projects tests/test_vikunja.py::test_get_project tests/test_vikunja.py::test_create_project tests/test_vikunja.py::test_create_project_with_parent -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja project tools (list, get, create)"
```

---

## Task 4: Task tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_tasks_no_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 10, "title": "Buy milk", "description": "", "done": False,
         "due_date": None, "priority": 0, "project_id": 1, "labels": []}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_tasks())
    assert result[0]["id"] == 10
    mock_client.get.assert_called_once_with("/tasks", params={"sort_by": "id", "order_by": "asc", "page": 1})


def test_list_tasks_with_project_id():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_tasks(project_id=5)
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project_id=5"


def test_list_tasks_project_id_combined_with_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_tasks(project_id=5, filter_by="done=false")
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project_id=5 && done=false"


def test_get_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [], "related_tasks": {}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_task(10))
    assert result["id"] == 10
    mock_client.get.assert_called_once_with("/tasks/10")


def test_create_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 11, "title": "New task", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_task(project_id=1, title="New task"))
    assert result["id"] == 11
    mock_client.put.assert_called_once_with("/projects/1/tasks", json={"title": "New task"})


def test_update_task_partial():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy oat milk", "done": False, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.update_task(10, title="Buy oat milk"))
    assert result["title"] == "Buy oat milk"
    mock_client.post.assert_called_once_with("/tasks/10", json={"title": "Buy oat milk"})


def test_update_task_done():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "done": True, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.update_task(10, done="true")
    mock_client.post.assert_called_once_with("/tasks/10", json={"done": True})


def test_delete_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "The task was successfully deleted."}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_task(10))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_tasks_no_filter tests/test_vikunja.py::test_get_task tests/test_vikunja.py::test_create_task -v
```

Expected: `AttributeError: module has no attribute 'list_tasks'`

- [ ] **Step 3: Implement task tools in vikunja.py**

Add a `_task_summary` helper and task functions before `register()`:

```python
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
```

Update `register()`:

```python
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
    ]:
        mcp.tool()(fn)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_tasks_no_filter tests/test_vikunja.py::test_list_tasks_with_project_id tests/test_vikunja.py::test_list_tasks_project_id_combined_with_filter tests/test_vikunja.py::test_get_task tests/test_vikunja.py::test_create_task tests/test_vikunja.py::test_update_task_partial tests/test_vikunja.py::test_update_task_done tests/test_vikunja.py::test_delete_task -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja task tools (list, get, create, update, delete)"
```

---

## Task 5: Label tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_labels():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "urgent", "hex_color": "ff0000", "description": ""},
        {"id": 2, "title": "home", "hex_color": "", "description": ""},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_labels())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "urgent"
    mock_client.get.assert_called_once_with("/labels")


def test_add_task_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {"label_id": 1, "created": "2024-01-01T00:00:00Z"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_label(task_id=10, label_id=1))
    assert result["status"] == "added"
    mock_client.put.assert_called_once_with("/tasks/10/labels", json={"label_id": 1})


def test_remove_task_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.remove_task_label(task_id=10, label_id=1))
    assert result["status"] == "removed"
    mock_client.delete.assert_called_once_with("/tasks/10/labels/1")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_labels tests/test_vikunja.py::test_add_task_label tests/test_vikunja.py::test_remove_task_label -v
```

Expected: `AttributeError: module has no attribute 'list_labels'`

- [ ] **Step 3: Implement label tools in vikunja.py**

Add before `register()`:

```python
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
```

Update `register()` to add the three label functions after `delete_task`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_labels tests/test_vikunja.py::test_add_task_label tests/test_vikunja.py::test_remove_task_label -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja label tools (list, add to task, remove from task)"
```

---

## Task 6: Comment tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_task_comments():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "comment": "First note", "created": "2024-01-01T00:00:00Z",
         "author": {"username": "charlie"}}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_task_comments(10))
    assert result[0]["id"] == 1
    assert result[0]["comment"] == "First note"
    mock_client.get.assert_called_once_with("/tasks/10/comments")


def test_add_task_comment():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 2, "comment": "Follow up needed", "created": "2024-01-02T00:00:00Z",
        "author": {"username": "charlie"}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_comment(10, "Follow up needed"))
    assert result["id"] == 2
    mock_client.put.assert_called_once_with("/tasks/10/comments", json={"comment": "Follow up needed"})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_comments tests/test_vikunja.py::test_add_task_comment -v
```

Expected: `AttributeError: module has no attribute 'list_task_comments'`

- [ ] **Step 3: Implement comment tools in vikunja.py**

Add before `register()`:

```python
def list_task_comments(task_id: int) -> str:
    """Get all comments on a Vikunja task."""
    with _client() as c:
        r = c.get(f"/tasks/{task_id}/comments")
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


def add_task_comment(task_id: int, comment: str) -> str:
    """Add a comment to a Vikunja task."""
    with _client() as c:
        r = c.put(f"/tasks/{task_id}/comments", json={"comment": comment})
        r.raise_for_status()
    data = r.json()
    return json.dumps({
        "id": data.get("id"),
        "comment": data.get("comment", ""),
        "created": data.get("created"),
    })
```

Update `register()` to add the two comment functions.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_comments tests/test_vikunja.py::test_add_task_comment -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja comment tools (list, add)"
```

---

## Task 7: Relation tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

Relations are embedded in the task's `related_tasks` dict (keyed by relation kind). Delete uses kind + other task ID in the URL path, not a relation ID.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_task_relations():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Task A", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [],
        "related_tasks": {"subtask": [{"id": 11, "title": "Sub A"}]}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_task_relations(10))
    assert "subtask" in result
    assert result["subtask"][0]["id"] == 11


def test_add_task_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "task_id": 10, "other_task_id": 11, "relation_kind": "subtask", "created": "2024-01-01T00:00:00Z"
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_relation(10, 11, "subtask"))
    assert result["status"] == "created"
    mock_client.put.assert_called_once_with(
        "/tasks/10/relations", json={"other_task_id": 11, "relation_kind": "subtask"}
    )


def test_delete_task_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_task_relation(10, "subtask", 11))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10/relations/subtask/11")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_relations tests/test_vikunja.py::test_add_task_relation tests/test_vikunja.py::test_delete_task_relation -v
```

Expected: `AttributeError: module has no attribute 'list_task_relations'`

- [ ] **Step 3: Implement relation tools in vikunja.py**

Add before `register()`:

```python
def list_task_relations(task_id: int) -> str:
    """Get all relations for a Vikunja task. Returns a dict keyed by relation kind (e.g. 'subtask', 'blocking')."""
    with _client() as c:
        r = c.get(f"/tasks/{task_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("related_tasks", {}))


def add_task_relation(task_id: int, other_task_id: int, relation_kind: str) -> str:
    """Create a relation between two Vikunja tasks. relation_kind: subtask, parenttask, related, duplicateof, duplicates, blocking, blocked, precedes, follows, copiedfrom, copiedto."""
    with _client() as c:
        r = c.put(f"/tasks/{task_id}/relations", json={"other_task_id": other_task_id, "relation_kind": relation_kind})
        r.raise_for_status()
    return json.dumps({"status": "created", "task_id": task_id, "other_task_id": other_task_id, "relation_kind": relation_kind})


def delete_task_relation(task_id: int, relation_kind: str, other_task_id: int) -> str:
    """Remove a relation between two Vikunja tasks. relation_kind and other_task_id must match an existing relation."""
    with _client() as c:
        r = c.delete(f"/tasks/{task_id}/relations/{relation_kind}/{other_task_id}")
        r.raise_for_status()
    return json.dumps({"status": "deleted", "task_id": task_id, "relation_kind": relation_kind, "other_task_id": other_task_id})
```

Update `register()` to add the three relation functions.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_relations tests/test_vikunja.py::test_add_task_relation tests/test_vikunja.py::test_delete_task_relation -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja relation tools (list, add, delete)"
```

---

## Task 8: Reminder tools

**Files:**
- Modify: `gateway/tools/vikunja.py`
- Modify: `tests/test_vikunja.py`

Reminders have no dedicated endpoints — they're embedded in the task model. `list_task_reminders` reads the task; `set_task_reminders` replaces the full reminders array via task update. The LLM workflow: call `list_task_reminders` to see current reminders, then call `set_task_reminders` with the complete new list.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_vikunja.py`:

```python
def test_list_task_reminders():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Task", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {},
        "reminders": [{"reminder": "2024-06-01T09:00:00Z", "relative_period": 0}]
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_task_reminders(10))
    assert len(result) == 1
    assert result[0]["reminder"] == "2024-06-01T09:00:00Z"
    mock_client.get.assert_called_once_with("/tasks/10")


def test_set_task_reminders():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Task", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {},
        "reminders": [{"reminder": "2024-06-01T09:00:00Z", "relative_period": 0}]
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.set_task_reminders(10, '[{"reminder": "2024-06-01T09:00:00Z"}]'))
    assert result["status"] == "updated"
    mock_client.post.assert_called_once_with(
        "/tasks/10", json={"reminders": [{"reminder": "2024-06-01T09:00:00Z"}]}
    )


def test_set_task_reminders_empty_clears_all():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Task", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "related_tasks": {}, "reminders": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.set_task_reminders(10, "[]")
    mock_client.post.assert_called_once_with("/tasks/10", json={"reminders": []})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_reminders tests/test_vikunja.py::test_set_task_reminders -v
```

Expected: `AttributeError: module has no attribute 'list_task_reminders'`

- [ ] **Step 3: Implement reminder tools in vikunja.py**

Add before `register()`:

```python
def list_task_reminders(task_id: int) -> str:
    """Get all reminders for a Vikunja task. Each reminder has a 'reminder' field (ISO 8601 datetime)."""
    with _client() as c:
        r = c.get(f"/tasks/{task_id}")
        r.raise_for_status()
    return json.dumps(r.json().get("reminders", []))


def set_task_reminders(task_id: int, reminders_json: str) -> str:
    """Replace all reminders on a Vikunja task. reminders_json is a JSON array of reminder objects, e.g. '[{"reminder": "2024-12-01T09:00:00Z"}]'. Pass '[]' to clear all reminders. Call list_task_reminders first to see existing reminders before modifying."""
    reminders = json.loads(reminders_json)
    with _client() as c:
        r = c.post(f"/tasks/{task_id}", json={"reminders": reminders})
        r.raise_for_status()
    return json.dumps({"status": "updated", "task_id": task_id, "reminders": r.json().get("reminders", [])})
```

Update `register()` to add the two reminder functions.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_vikunja.py::test_list_task_reminders tests/test_vikunja.py::test_set_task_reminders tests/test_vikunja.py::test_set_task_reminders_empty_clears_all -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/vikunja.py tests/test_vikunja.py
git commit -m "feat: add Vikunja reminder tools (list, set)"
```

---

## Task 9: Wire into main.py and run full test suite

**Files:**
- Modify: `gateway/main.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_vikunja.py`:

```python
def test_vikunja_registered_in_server():
    from gateway.config import Config
    from gateway import main

    config = Config()
    mcp = main.create_server(config)
    assert mcp is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_vikunja.py::test_vikunja_registered_in_server -v
```

Expected: `ImportError` — vikunja not yet imported in main.py

- [ ] **Step 3: Wire vikunja into main.py**

In `gateway/main.py`:

Change the import line:
```python
from gateway.tools import calendar, reminders, contacts, email, obsidian, karakeep, owntracks
```
to:
```python
from gateway.tools import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, vikunja
```

In `create_server()`, after `owntracks.init(config.owntracks)` and `owntracks.register(mcp)`, add:
```python
    vikunja.init(config.vikunja)
    vikunja.register(mcp)
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (26 total)

- [ ] **Step 5: Commit**

```bash
git add gateway/main.py
git commit -m "feat: wire Vikunja tools into gateway MCP server"
```
