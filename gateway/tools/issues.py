from __future__ import annotations
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import yaml
from gateway.config import ObsidianConfig

_config: ObsidianConfig | None = None
_ISSUES_DIR = "Projects/_issues"


def init(config: ObsidianConfig) -> None:
    global _config
    _config = config


def _vault() -> Path:
    assert _config and _config.vault_path, "GATEWAY_OBSIDIAN__VAULT_PATH not configured"
    return Path(_config.vault_path).expanduser()


def _issues_dir() -> Path:
    d = _vault() / _ISSUES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:60]) or "issue"


def _next_id() -> int:
    ids = [
        int(m.group(1))
        for f in _issues_dir().glob("*.md")
        if (m := re.match(r"^(\d+)-", f.name))
    ]
    return max(ids, default=0) + 1


def _find_file(issue_id: int) -> Path | None:
    prefix = f"{issue_id:04d}-"
    for f in _issues_dir().glob("*.md"):
        if f.name.startswith(prefix):
            return f
    return None


def _normalize_dates(fm: dict) -> dict:
    """Convert yaml-parsed date/datetime objects back to ISO strings."""
    result: dict[str, Any] = {}
    for k, v in fm.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, date):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = [
                i.isoformat() if isinstance(i, (date, datetime)) else i
                for i in v
            ]
        elif isinstance(v, dict):
            result[k] = _normalize_dates(v)
        else:
            result[k] = v
    return result


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (fm_dict, body_text)."""
    if content.startswith("---\n"):
        parts = content[4:].split("\n---\n", 1)
        if len(parts) == 2:
            return _normalize_dates(yaml.safe_load(parts[0]) or {}), parts[1]
    return {}, content


def _parse_body(body: str) -> tuple[str, list[dict], list[dict]]:
    """Parse body into (description, checklist, comments)."""
    description = ""
    checklist: list[dict] = []
    comments: list[dict] = []
    checklist_raw = ""
    comments_raw = ""

    if "## Checklist" in body:
        desc_raw, rest = body.split("## Checklist", 1)
        description = desc_raw.strip()
        if "## Comments" in rest:
            checklist_raw, comments_raw = rest.split("## Comments", 1)
        else:
            checklist_raw = rest
    elif "## Comments" in body:
        desc_raw, comments_raw = body.split("## Comments", 1)
        description = desc_raw.strip()
    else:
        description = body.strip()

    for line in checklist_raw.splitlines():
        s = line.strip()
        if s.startswith("- [x] "):
            checklist.append({"text": s[6:], "done": True})
        elif s.startswith("- [ ] "):
            checklist.append({"text": s[6:], "done": False})

    if comments_raw.strip():
        for block in re.split(r"\n###\s+", "\n" + comments_raw):
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            timestamp = lines[0].strip()
            text = "\n".join(lines[1:]).strip()
            if timestamp and text:
                comments.append({"timestamp": timestamp, "text": text})

    return description, checklist, comments


def _render_file(
    fm: dict,
    description: str,
    checklist: list[dict],
    comments: list[dict],
) -> str:
    """Render a complete issue file as a string."""
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    parts = [f"---\n{fm_yaml}---\n\n"]
    if description:
        parts.append(f"{description}\n\n")
    parts.append("## Checklist\n\n")
    for item in checklist:
        mark = "x" if item.get("done") else " "
        parts.append(f"- [{mark}] {item['text']}\n")
    parts.append("\n## Comments\n")
    for c in comments:
        parts.append(f"\n### {c['timestamp']}\n\n{c['text']}\n")
    return "".join(parts)


def _read_issue(issue_id: int) -> tuple[Path, dict, str, list[dict], list[dict]]:
    """Find and fully parse an issue. Returns (path, fm, description, checklist, comments)."""
    f = _find_file(issue_id)
    if f is None:
        raise FileNotFoundError(f"Issue #{issue_id} not found")
    content = f.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(content)
    description, checklist, comments = _parse_body(body)
    return f, fm, description, checklist, comments


def list_issues(
    project: str = "",
    status: str = "",
    priority: int = -1,
    label: str = "",
) -> str:
    """List issues in Projects/_issues/. Filter by project name, status (open/in-progress/done), priority (0-5, -1=all), or label."""
    results = []
    for f in sorted(_issues_dir().glob("*.md")):
        content = f.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(content)
        if not fm.get("id"):
            continue
        if project and fm.get("project", "") != project:
            continue
        if status and fm.get("status", "") != status:
            continue
        if priority >= 0 and fm.get("priority", 0) != priority:
            continue
        if label and label not in (fm.get("labels") or []):
            continue
        results.append({
            "id": fm.get("id"),
            "title": fm.get("title", ""),
            "project": fm.get("project", ""),
            "status": fm.get("status", "open"),
            "priority": fm.get("priority", 0),
            "due": fm.get("due", ""),
            "labels": fm.get("labels") or [],
        })
    return json.dumps(results)


def get_issue(issue_id: int) -> str:
    """Get a single issue by numeric ID. Returns full detail including checklist and comments."""
    try:
        _, fm, description, checklist, comments = _read_issue(issue_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({
        "id": fm.get("id"),
        "title": fm.get("title", ""),
        "project": fm.get("project", ""),
        "status": fm.get("status", "open"),
        "priority": fm.get("priority", 0),
        "due": fm.get("due", ""),
        "labels": fm.get("labels") or [],
        "reminders": fm.get("reminders") or [],
        "related": fm.get("related") or [],
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
    """Create a new issue in Projects/_issues/. Returns the new issue id, title, and vault-relative path."""
    issue_id = _next_id()
    slug = _slugify(title)
    filename = f"{issue_id:04d}-{slug}.md" if slug else f"{issue_id:04d}.md"

    fm: dict[str, Any] = {
        "id": issue_id,
        "title": title,
        "project": project,
        "status": "open",
        "priority": priority,
    }
    if due:
        fm["due"] = due
    if labels:
        fm["labels"] = labels
    if reminders:
        fm["reminders"] = reminders
    if related:
        fm["related"] = related

    checklist = [{"text": item, "done": False} for item in (checklist_items or [])]
    content = _render_file(fm, description, checklist, [])
    path = _issues_dir() / filename
    path.write_text(content, encoding="utf-8")

    return json.dumps({
        "id": issue_id,
        "title": title,
        "path": str(path.relative_to(_vault())),
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
    """Update an issue. Only non-empty/non-default arguments are applied. priority=-1 means unchanged."""
    try:
        f, fm, existing_description, checklist, comments = _read_issue(issue_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    if status and status not in {"open", "in-progress", "done"}:
        return json.dumps({"error": f"Invalid status: {status!r}. Must be one of: open, in-progress, done"})

    if title:
        fm["title"] = title
    if status:
        fm["status"] = status
    if project:
        fm["project"] = project
    if due:
        fm["due"] = due
    if priority >= 0:
        fm["priority"] = priority
    if labels is not None:
        fm["labels"] = labels
    if reminders is not None:
        fm["reminders"] = reminders
    if related is not None:
        fm["related"] = related

    new_description = description if description else existing_description
    content = _render_file(fm, new_description, checklist, comments)
    f.write_text(content, encoding="utf-8")
    return json.dumps({"status": "updated", "id": issue_id})


def delete_issue(issue_id: int) -> str:
    """Delete an issue by numeric ID."""
    f = _find_file(issue_id)
    if f is None:
        return json.dumps({"error": f"Issue #{issue_id} not found"})
    f.unlink()
    return json.dumps({"status": "deleted", "id": issue_id})


def add_issue_comment(issue_id: int, comment: str) -> str:
    """Append a timestamped comment to an issue."""
    try:
        f, fm, description, checklist, comments = _read_issue(issue_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    comments.append({"timestamp": timestamp, "text": comment})
    f.write_text(_render_file(fm, description, checklist, comments), encoding="utf-8")
    return json.dumps({"status": "added", "id": issue_id, "timestamp": timestamp})


def add_checklist_item(issue_id: int, item: str) -> str:
    """Append a new unchecked checklist item to an issue."""
    try:
        f, fm, description, checklist, comments = _read_issue(issue_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    checklist.append({"text": item, "done": False})
    f.write_text(_render_file(fm, description, checklist, comments), encoding="utf-8")
    return json.dumps({"status": "added", "id": issue_id, "item": item})


def toggle_checklist_item(issue_id: int, item_text: str) -> str:
    """Flip done/undone for the checklist item whose text matches item_text exactly."""
    try:
        f, fm, description, checklist, comments = _read_issue(issue_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    for item in checklist:
        if item["text"] == item_text:
            item["done"] = not item["done"]
            f.write_text(_render_file(fm, description, checklist, comments), encoding="utf-8")
            return json.dumps({"status": "toggled", "id": issue_id, "item": item_text, "done": item["done"]})
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
