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


def register(mcp) -> None:
    for fn in [
        list_projects,
        get_project,
        create_project,
    ]:
        mcp.tool()(fn)
