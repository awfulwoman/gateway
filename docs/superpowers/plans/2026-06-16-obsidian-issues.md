# Obsidian Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Vikunja with Obsidian-backed issue tracking — markdown files in `Projects/_issues/`, managed via new MCP tools and `gw issues` CLI commands.

**Architecture:** New `gateway/tools/issues.py` (MCP tools) and `gateway/cli/commands/issues.py` (CLI) replace `vikunja.py` equivalents. Issues are markdown files with YAML frontmatter stored in `<vault>/Projects/_issues/`. The `obsidian` module's `ObsidianConfig` is reused for the vault path.

**Tech Stack:** Python, PyYAML, Click, FastMCP, pytest with `tmp_path` for filesystem tests.

---

## File Map

| Action | Path |
|--------|------|
| Create | `gateway/tools/issues.py` |
| Create | `gateway/cli/commands/issues.py` |
| Create | `tests/test_issues.py` |
| Create | `tests/cli/test_issues.py` |
| Modify | `pyproject.toml` |
| Modify | `gateway/main.py` |
| Modify | `gateway/config.py` |
| Modify | `gateway/cli/__init__.py` |
| Modify | `gateway/cli/fmt.py` |
| Modify | `tests/cli/test_fmt.py` |
| Delete | `gateway/tools/vikunja.py` |
| Delete | `gateway/cli/commands/vikunja.py` |
| Delete | `tests/test_vikunja.py` |
| Delete | `tests/cli/test_vikunja.py` |

---

## Task 1: Add PyYAML dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pyyaml to project dependencies**

In `pyproject.toml`, add `"pyyaml>=6.0"` to the `dependencies` list:

```toml
dependencies = [
    "click>=8.0",
    "mcp[cli]>=1.0",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",
    "pyobjc-framework-EventKit>=10",
    "pyobjc-framework-Contacts>=10",
    "pyobjc-framework-CoreLocation>=10",
    "httpx>=0.25",
]
```

- [ ] **Step 2: Sync the lockfile**

```bash
uv sync
```

Expected: lockfile updated, no errors.

- [ ] **Step 3: Verify PyYAML importable**

```bash
uv run python -c "import yaml; print(yaml.__version__)"
```

Expected: prints a version string like `6.0.2`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pyyaml dependency for Obsidian issues"
```

---

## Task 2: issues.py — private helpers

**Files:**
- Create: `gateway/tools/issues.py`
- Create: `tests/test_issues.py`

These helpers handle all file I/O and parsing. The public MCP tool functions (Tasks 3–6) are built on top of them.

- [ ] **Step 1: Write failing tests for helpers**

Create `tests/test_issues.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
import pytest
import gateway.tools.issues as issues
from gateway.config import ObsidianConfig

SAMPLE = """\
---
id: 42
title: Fix login bug
project: MyProject
status: open
priority: 2
due: '2026-07-01'
labels:
- bug
reminders:
- '2026-06-30T09:00:00Z'
related:
- 17
---

Description prose here.

## Checklist

- [ ] First step
- [x] Done step

## Comments

### 2026-06-16T10:30

First comment.
"""


@pytest.fixture
def vault(tmp_path):
    issues.init(ObsidianConfig(vault_path=str(tmp_path)))
    return tmp_path


def test_slugify_basic():
    assert issues._slugify("Fix login bug") == "fix-login-bug"


def test_slugify_special_chars():
    assert issues._slugify("Can't connect to DB!") == "cant-connect-to-db"


def test_slugify_long_title():
    assert len(issues._slugify("a" * 100)) <= 60


def test_next_id_empty(vault):
    assert issues._next_id() == 1


def test_next_id_increments(vault):
    d = vault / "Projects" / "_issues"
    d.mkdir(parents=True)
    (d / "0001-first.md").write_text("")
    (d / "0003-third.md").write_text("")
    assert issues._next_id() == 4


def test_find_file(vault):
    d = vault / "Projects" / "_issues"
    d.mkdir(parents=True)
    f = d / "0042-test.md"
    f.write_text("x")
    assert issues._find_file(42) == f


def test_find_file_missing(vault):
    assert issues._find_file(99) is None


def test_parse_frontmatter():
    fm, body = issues._parse_frontmatter(SAMPLE)
    assert fm["id"] == 42
    assert fm["title"] == "Fix login bug"
    assert fm["labels"] == ["bug"]
    assert fm["related"] == [17]


def test_parse_body():
    _, body = issues._parse_frontmatter(SAMPLE)
    description, checklist, comments = issues._parse_body(body)
    assert description == "Description prose here."
    assert checklist == [
        {"text": "First step", "done": False},
        {"text": "Done step", "done": True},
    ]
    assert len(comments) == 1
    assert comments[0]["timestamp"] == "2026-06-16T10:30"
    assert comments[0]["text"] == "First comment."


def test_render_roundtrip():
    fm = {
        "id": 1, "title": "Test issue", "project": "P",
        "status": "open", "priority": 0,
        "due": "2026-07-01", "labels": ["bug"], "reminders": [], "related": [],
    }
    checklist = [{"text": "Do thing", "done": False}]
    comments = [{"timestamp": "2026-06-16T10:00", "text": "A comment"}]
    content = issues._render_file(fm, "Description.", checklist, comments)

    fm2, body = issues._parse_frontmatter(content)
    desc, checks, cmts = issues._parse_body(body)

    assert fm2["id"] == 1
    assert fm2["title"] == "Test issue"
    assert fm2["due"] == "2026-07-01"
    assert desc == "Description."
    assert checks == checklist
    assert cmts == comments
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_issues.py -v
```

Expected: `ModuleNotFoundError` or similar — `gateway.tools.issues` doesn't exist yet.

- [ ] **Step 3: Create gateway/tools/issues.py with helpers**

```python
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
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
    return s[:60]


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
    import datetime as dt
    result: dict[str, Any] = {}
    for k, v in fm.items():
        if isinstance(v, dt.datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dt.date):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = [
                i.isoformat() if isinstance(i, (dt.date, dt.datetime)) else i
                for i in v
            ]
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


def register(mcp) -> None:
    pass  # populated in later tasks
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/test_issues.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/issues.py tests/test_issues.py
git commit -m "feat: add Obsidian issues tool module — helpers and file parsing"
```

---

## Task 3: issues.py — list_issues and get_issue

**Files:**
- Modify: `gateway/tools/issues.py`
- Modify: `tests/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_issues.py`:

```python
def test_list_issues_empty(vault):
    result = json.loads(issues.list_issues())
    assert result == []


def test_list_issues_returns_summary(vault):
    (vault / "Projects" / "_issues").mkdir(parents=True)
    (vault / "Projects" / "_issues" / "0001-test.md").write_text(
        "---\nid: 1\ntitle: Test\nproject: Gateway\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n"
    )
    result = json.loads(issues.list_issues())
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["title"] == "Test"
    assert result[0]["project"] == "Gateway"
    assert "checklist" not in result[0]
    assert "comments" not in result[0]


def test_list_issues_filter_project(vault):
    d = vault / "Projects" / "_issues"
    d.mkdir(parents=True)
    (d / "0001-alpha.md").write_text("---\nid: 1\ntitle: A\nproject: Alpha\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    (d / "0002-beta.md").write_text("---\nid: 2\ntitle: B\nproject: Beta\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    result = json.loads(issues.list_issues(project="Alpha"))
    assert len(result) == 1
    assert result[0]["title"] == "A"


def test_list_issues_filter_status(vault):
    d = vault / "Projects" / "_issues"
    d.mkdir(parents=True)
    (d / "0001-open.md").write_text("---\nid: 1\ntitle: Open\nproject: P\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    (d / "0002-done.md").write_text("---\nid: 2\ntitle: Done\nproject: P\nstatus: done\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    result = json.loads(issues.list_issues(status="open"))
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_get_issue_not_found(vault):
    result = json.loads(issues.get_issue(99))
    assert "error" in result


def test_get_issue_full_detail(vault):
    d = vault / "Projects" / "_issues"
    d.mkdir(parents=True)
    (d / "0042-test.md").write_text(SAMPLE)
    result = json.loads(issues.get_issue(42))
    assert result["id"] == 42
    assert result["title"] == "Fix login bug"
    assert result["description"] == "Description prose here."
    assert result["checklist"] == [
        {"text": "First step", "done": False},
        {"text": "Done step", "done": True},
    ]
    assert result["comments"][0]["text"] == "First comment."
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_issues.py::test_list_issues_empty tests/test_issues.py::test_get_issue_not_found -v
```

Expected: `AttributeError: module 'gateway.tools.issues' has no attribute 'list_issues'`.

- [ ] **Step 3: Add list_issues and get_issue to gateway/tools/issues.py**

Add these functions before the `register()` function:

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/test_issues.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/issues.py tests/test_issues.py
git commit -m "feat: add list_issues and get_issue MCP tools"
```

---

## Task 4: issues.py — create_issue

**Files:**
- Modify: `gateway/tools/issues.py`
- Modify: `tests/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_issues.py`:

```python
def test_create_assigns_id_1_when_empty(vault):
    result = json.loads(issues.create_issue("First issue"))
    assert result["id"] == 1


def test_create_filename_format(vault):
    issues.create_issue("Fix Login Bug")
    files = list((vault / "Projects" / "_issues").glob("*.md"))
    assert len(files) == 1
    assert files[0].name == "0001-fix-login-bug.md"


def test_create_sequential_ids(vault):
    issues.create_issue("First")
    issues.create_issue("Second")
    issues.create_issue("Third")
    r = json.loads(issues.get_issue(3))
    assert r["id"] == 3
    assert r["title"] == "Third"


def test_create_stores_all_fields(vault):
    issues.create_issue(
        "My issue",
        project="Gateway",
        description="Details here",
        due="2026-07-01",
        priority=2,
        labels=["bug", "urgent"],
        reminders=["2026-06-30T09:00:00Z"],
        related=[5],
        checklist_items=["Step 1", "Step 2"],
    )
    result = json.loads(issues.get_issue(1))
    assert result["project"] == "Gateway"
    assert result["description"] == "Details here"
    assert result["due"] == "2026-07-01"
    assert result["priority"] == 2
    assert result["labels"] == ["bug", "urgent"]
    assert result["related"] == [5]
    assert result["checklist"] == [
        {"text": "Step 1", "done": False},
        {"text": "Step 2", "done": False},
    ]


def test_create_status_defaults_to_open(vault):
    issues.create_issue("Issue")
    result = json.loads(issues.get_issue(1))
    assert result["status"] == "open"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_issues.py::test_create_assigns_id_1_when_empty -v
```

Expected: `AttributeError: module ... has no attribute 'create_issue'`.

- [ ] **Step 3: Add create_issue to gateway/tools/issues.py**

Add before `register()`:

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/test_issues.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/issues.py tests/test_issues.py
git commit -m "feat: add create_issue MCP tool"
```

---

## Task 5: issues.py — update_issue and delete_issue

**Files:**
- Modify: `gateway/tools/issues.py`
- Modify: `tests/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_issues.py`:

```python
def test_update_title(vault):
    issues.create_issue("Original")
    issues.update_issue(1, title="Updated")
    assert json.loads(issues.get_issue(1))["title"] == "Updated"


def test_update_status(vault):
    issues.create_issue("Issue")
    issues.update_issue(1, status="in-progress")
    assert json.loads(issues.get_issue(1))["status"] == "in-progress"


def test_update_not_found(vault):
    result = json.loads(issues.update_issue(99, title="x"))
    assert "error" in result


def test_delete_issue(vault):
    issues.create_issue("To delete")
    issues.delete_issue(1)
    result = json.loads(issues.get_issue(1))
    assert "error" in result


def test_delete_not_found(vault):
    result = json.loads(issues.delete_issue(99))
    assert "error" in result
```

- [ ] **Step 2: Run tests (excluding the comment-dependent one) — expect failures**

```bash
uv run pytest tests/test_issues.py::test_update_title tests/test_issues.py::test_delete_issue -v
```

Expected: `AttributeError` — functions don't exist yet.

- [ ] **Step 3: Add update_issue and delete_issue to gateway/tools/issues.py**

Add before `register()`:

```python
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
```

- [ ] **Step 4: Run all tests (except comment-dependent one) — expect pass**

```bash
uv run pytest tests/test_issues.py -v -k "not preserves_checklist_and_comments"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/issues.py tests/test_issues.py
git commit -m "feat: add update_issue and delete_issue MCP tools"
```

---

## Task 6: issues.py — comments, checklist ops, and register()

**Files:**
- Modify: `gateway/tools/issues.py`
- Modify: `tests/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_issues.py`:

```python
def test_add_comment(vault):
    issues.create_issue("Issue")
    issues.add_issue_comment(1, "First comment")
    result = json.loads(issues.get_issue(1))
    assert len(result["comments"]) == 1
    assert result["comments"][0]["text"] == "First comment"


def test_add_comment_appends(vault):
    issues.create_issue("Issue")
    issues.add_issue_comment(1, "Comment A")
    issues.add_issue_comment(1, "Comment B")
    result = json.loads(issues.get_issue(1))
    assert len(result["comments"]) == 2
    assert result["comments"][1]["text"] == "Comment B"


def test_add_checklist_item(vault):
    issues.create_issue("Issue")
    issues.add_checklist_item(1, "New task")
    result = json.loads(issues.get_issue(1))
    assert any(c["text"] == "New task" for c in result["checklist"])
    assert result["checklist"][-1]["done"] is False


def test_toggle_checklist_item_to_done(vault):
    issues.create_issue("Issue", checklist_items=["Do thing"])
    issues.toggle_checklist_item(1, "Do thing")
    result = json.loads(issues.get_issue(1))
    assert result["checklist"][0]["done"] is True


def test_toggle_checklist_item_back_to_undone(vault):
    issues.create_issue("Issue", checklist_items=["Do thing"])
    issues.toggle_checklist_item(1, "Do thing")
    issues.toggle_checklist_item(1, "Do thing")
    result = json.loads(issues.get_issue(1))
    assert result["checklist"][0]["done"] is False


def test_toggle_checklist_item_not_found(vault):
    issues.create_issue("Issue")
    result = json.loads(issues.toggle_checklist_item(1, "Nonexistent"))
    assert "error" in result


def test_update_preserves_checklist_and_comments(vault):
    issues.create_issue("Issue", checklist_items=["Step 1"])
    issues.add_issue_comment(1, "A comment")
    issues.update_issue(1, status="done")
    result = json.loads(issues.get_issue(1))
    assert len(result["checklist"]) == 1
    assert len(result["comments"]) == 1


def test_issues_registered_in_server():
    from gateway.config import Config
    from gateway import main as gw_main
    config = Config()
    mcp = gw_main.create_server(config)
    assert mcp is not None
```

Note: `test_issues_registered_in_server` will fail until Task 11 (wiring). Run it last.

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_issues.py::test_add_comment tests/test_issues.py::test_add_checklist_item tests/test_issues.py::test_toggle_checklist_item_to_done -v
```

Expected: `AttributeError` — functions don't exist yet.

- [ ] **Step 3: Add comment/checklist functions and update register() in gateway/tools/issues.py**

Add before `register()`:

```python
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
```

Replace the stub `register()` with the full version:

```python
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
```

- [ ] **Step 4: Run all tool tests (excluding server registration test) — expect pass**

```bash
uv run pytest tests/test_issues.py -v -k "not registered_in_server"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/tools/issues.py tests/test_issues.py
git commit -m "feat: add comment/checklist MCP tools and register issues"
```

---

## Task 7: Update fmt.py formatters

**Files:**
- Modify: `gateway/cli/fmt.py`
- Modify: `tests/cli/test_fmt.py`

The `issues()` and `issue_detail()` formatters currently use Vikunja fields (`done`, `due_date`, `project_id`, `labels` as list of dicts). Update them for the new data model (`status`, `due`, `project`, `labels` as list of strings, plus `checklist` and `comments`). Also remove the `projects()` and `comments()` formatters (no longer needed by issues CLI — keep `comments()` in place to avoid breaking anything but remove `projects()`).

- [ ] **Step 1: Update failing tests in tests/cli/test_fmt.py**

Replace the `test_issues`, `test_issues_done`, `test_issue_detail` tests and delete `test_projects`, `test_projects_empty`, `test_comments`, `test_comments_empty` tests. The new tests:

```python
# Replace existing issues/issue_detail/projects/comments tests with:

def test_issues_empty():
    assert fmt.issues([]) == "No issues."


def test_issues():
    data = [{"id": 42, "title": "Write tests", "status": "open",
              "due": "2026-07-01", "priority": 2, "project": "Gateway", "labels": ["dev"]}]
    out = fmt.issues(data)
    assert "#42" in out
    assert "Write tests" in out
    assert "2026-07-01" in out
    assert "[Gateway]" in out


def test_issues_done():
    data = [{"id": 1, "title": "Done thing", "status": "done",
              "due": "", "priority": 0, "project": "", "labels": []}]
    out = fmt.issues(data)
    assert "[x]" in out


def test_issue_detail():
    t = {
        "id": 42, "title": "Write tests", "status": "open",
        "due": "2026-07-01", "priority": 2, "project": "Gateway",
        "description": "Needs TDD", "labels": ["urgent"], "related": [17],
        "reminders": [], "checklist": [{"text": "Draft tests", "done": False}],
        "comments": [{"timestamp": "2026-06-16T10:00", "text": "Started"}],
    }
    out = fmt.issue_detail(t)
    assert "#42" in out
    assert "Write tests" in out
    assert "Needs TDD" in out
    assert "urgent" in out
    assert "Draft tests" in out
    assert "Started" in out
    assert "#17" in out
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/cli/test_fmt.py::test_issues tests/cli/test_fmt.py::test_issue_detail -v
```

Expected: failures because `fmt.issues()` reads `done`/`due_date`/`project_id`.

- [ ] **Step 3: Update issues() and issue_detail() in gateway/cli/fmt.py**

Replace the existing `issues()` function:

```python
def issues(data: list) -> str:
    if not data:
        return "No issues."
    lines = []
    for t in data:
        mark = "x" if t.get("status") == "done" else " "
        due = f"  due:{t['due'][:10]}" if t.get("due") else ""
        pri = f"  p{t['priority']}" if t.get("priority") else ""
        proj = f"  [{t['project']}]" if t.get("project") else ""
        lines.append(f"[{mark}] #{t['id']}  {t['title']}{proj}{due}{pri}")
    return "\n".join(lines)
```

Replace the existing `issue_detail()` function:

```python
def issue_detail(t: dict) -> str:
    lines = [
        f"#{t['id']} {t['title']}",
        f"  Status:   {t.get('status', 'open')}",
        f"  Priority: {t.get('priority', 0)}",
        f"  Due:      {t.get('due') or '-'}",
        f"  Project:  {t.get('project') or '-'}",
    ]
    if t.get("description"):
        lines += ["", t["description"]]
    if t.get("labels"):
        lines.append(f"  Labels:   {', '.join(t['labels'])}")
    if t.get("related"):
        lines.append(f"  Related:  {', '.join('#' + str(i) for i in t['related'])}")
    if t.get("checklist"):
        lines.append("\nChecklist:")
        for item in t["checklist"]:
            mark = "x" if item.get("done") else " "
            lines.append(f"  [{mark}] {item['text']}")
    if t.get("comments"):
        lines.append("\nComments:")
        for c in t["comments"]:
            lines.append(f"  {c['timestamp']}: {c['text']}")
    return "\n".join(lines)
```

Also remove the `projects()` function from `fmt.py` (it will no longer be called):

```python
# Delete this function entirely:
def projects(data: list) -> str:
    ...
```

- [ ] **Step 4: Run fmt tests — expect pass**

```bash
uv run pytest tests/cli/test_fmt.py -v
```

Expected: all tests pass (the old `test_projects*` and `test_comments*` tests were deleted in Step 1).

- [ ] **Step 5: Commit**

```bash
git add gateway/cli/fmt.py tests/cli/test_fmt.py
git commit -m "feat: update fmt.py issue formatters for Obsidian data model"
```

---

## Task 8: CLI commands — list and get

**Files:**
- Create: `gateway/cli/commands/issues.py`
- Create: `tests/cli/test_issues.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cli/test_issues.py`:

```python
from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

ISSUE_SUMMARY = {
    "id": 42, "title": "Write tests", "project": "Gateway",
    "status": "open", "priority": 2, "due": "2026-07-01", "labels": ["dev"],
}
ISSUE_DETAIL = {
    **ISSUE_SUMMARY,
    "reminders": [], "related": [],
    "description": "Write unit tests",
    "checklist": [{"text": "Draft tests", "done": False}],
    "comments": [{"timestamp": "2026-06-16T10:00", "text": "Started"}],
}
ISSUES = [ISSUE_SUMMARY]

runner = CliRunner()


def test_issues_list():
    with patch("gateway.cli.client.call_tool", return_value=ISSUES) as mock:
        r = runner.invoke(main, ["issues", "list"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "", "status": "", "priority": -1, "label": ""},
    )


def test_issues_list_with_project():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["issues", "list", "--project", "Gateway"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "Gateway", "status": "", "priority": -1, "label": ""},
    )


def test_issues_list_with_status():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["issues", "list", "--status", "open"])
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "list_issues",
        {"project": "", "status": "open", "priority": -1, "label": ""},
    )


def test_issues_get():
    with patch("gateway.cli.client.call_tool", return_value=ISSUE_DETAIL) as mock:
        r = runner.invoke(main, ["issues", "get", "42"])
    assert r.exit_code == 0
    assert "Write tests" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "get_issue", {"issue_id": 42},
    )
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/cli/test_issues.py::test_issues_list tests/cli/test_issues.py::test_issues_get -v
```

Expected: `UsageError` or `No such command 'issues'` because the command group doesn't exist yet.

- [ ] **Step 3: Create gateway/cli/commands/issues.py with list and get**

```python
from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Issues (Obsidian vault)."""


@group.command("list")
@click.option("--project", default="")
@click.option("--status", default="")
@click.option("--priority", default=-1, type=int)
@click.option("--label", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_issues(obj: dict, project: str, status: str, priority: int, label: str, as_json: bool) -> None:
    """List issues."""
    try:
        data = client.call_tool(obj["server"], "list_issues", {
            "project": project, "status": status, "priority": priority, "label": label,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issues(data))


@group.command("get")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Get an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "get_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issue_detail(data))
```

- [ ] **Step 4: Wire the group temporarily in gateway/cli/__init__.py to unblock tests**

In `gateway/cli/__init__.py`, add the import and command (keep vikunja for now — it will be removed in Task 11):

```python
from gateway.cli.commands import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, vikunja, issues

# Add after existing add_command calls:
main.add_command(issues.group, "issues")
```

Also **remove** the vikunja issues/projects lines (replacing them):
```python
# Remove these two lines:
main.add_command(vikunja.tasks_group, "issues")
main.add_command(vikunja.projects_group, "projects")

# Replace with:
main.add_command(issues.group, "issues")
```

- [ ] **Step 5: Run tests — expect pass**

```bash
uv run pytest tests/cli/test_issues.py::test_issues_list tests/cli/test_issues.py::test_issues_get tests/cli/test_issues.py::test_issues_list_with_project tests/cli/test_issues.py::test_issues_list_with_status -v
```

Expected: all four tests pass.

- [ ] **Step 6: Commit**

```bash
git add gateway/cli/commands/issues.py gateway/cli/__init__.py tests/cli/test_issues.py
git commit -m "feat: add gw issues list and get CLI commands"
```

---

## Task 9: CLI commands — create, update, delete

**Files:**
- Modify: `gateway/cli/commands/issues.py`
- Modify: `tests/cli/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/cli/test_issues.py`:

```python
def test_issues_create():
    with patch("gateway.cli.client.call_tool", return_value={"id": 43, "title": "New issue", "path": "Projects/_issues/0043-new-issue.md"}) as mock:
        r = runner.invoke(main, ["issues", "create", "New issue", "--project", "Gateway"])
    assert r.exit_code == 0
    assert "43" in r.output
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "create_issue",
        {"title": "New issue", "project": "Gateway", "description": "", "due": "", "priority": 0, "labels": []},
    )


def test_issues_create_with_label():
    with patch("gateway.cli.client.call_tool", return_value={"id": 44, "title": "Bug", "path": "Projects/_issues/0044-bug.md"}) as mock:
        runner.invoke(main, ["issues", "create", "Bug", "--label", "bug", "--label", "urgent"])
    args = mock.call_args[0]
    assert args[2]["labels"] == ["bug", "urgent"]


def test_issues_update():
    with patch("gateway.cli.client.call_tool", return_value={"status": "updated", "id": 42}) as mock:
        r = runner.invoke(main, ["issues", "update", "42", "--status", "done"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "update_issue",
        {"issue_id": 42, "title": "", "status": "done", "project": "", "description": "", "due": "", "priority": -1},
    )


def test_issues_delete():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "id": 42}) as mock:
        r = runner.invoke(main, ["issues", "delete", "42"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "delete_issue", {"issue_id": 42},
    )
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/cli/test_issues.py::test_issues_create tests/cli/test_issues.py::test_issues_update tests/cli/test_issues.py::test_issues_delete -v
```

Expected: `No such command 'create'` etc.

- [ ] **Step 3: Add create, update, delete to gateway/cli/commands/issues.py**

Append to `gateway/cli/commands/issues.py`:

```python
@group.command("create")
@click.argument("title")
@click.option("--project", default="")
@click.option("--description", default="")
@click.option("--due", default="")
@click.option("--priority", default=0, type=int)
@click.option("--label", "labels", multiple=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_issue(obj: dict, title: str, project: str, description: str, due: str, priority: int, labels: tuple, as_json: bool) -> None:
    """Create a new issue."""
    try:
        data = client.call_tool(obj["server"], "create_issue", {
            "title": title, "project": project, "description": description,
            "due": due, "priority": priority, "labels": list(labels),
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")


@group.command("update")
@click.argument("issue-id", type=int)
@click.option("--title", default="")
@click.option("--status", default="", type=click.Choice(["", "open", "in-progress", "done"]))
@click.option("--project", default="")
@click.option("--description", default="")
@click.option("--due", default="")
@click.option("--priority", default=-1, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update_issue(obj: dict, issue_id: int, title: str, status: str, project: str, description: str, due: str, priority: int, as_json: bool) -> None:
    """Update an issue. Only supplied options are changed."""
    try:
        data = client.call_tool(obj["server"], "update_issue", {
            "issue_id": issue_id, "title": title, "status": status,
            "project": project, "description": description, "due": due, "priority": priority,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: #{issue_id}")


@group.command("delete")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Delete an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "delete_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: #{issue_id}")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/cli/test_issues.py -v
```

Expected: all tests added so far pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/cli/commands/issues.py tests/cli/test_issues.py
git commit -m "feat: add gw issues create, update, delete CLI commands"
```

---

## Task 10: CLI commands — comment, check, toggle

**Files:**
- Modify: `gateway/cli/commands/issues.py`
- Modify: `tests/cli/test_issues.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/cli/test_issues.py`:

```python
def test_issues_comment():
    with patch("gateway.cli.client.call_tool", return_value={"status": "added", "id": 42, "timestamp": "2026-06-16T10:00"}) as mock:
        r = runner.invoke(main, ["issues", "comment", "42", "LGTM"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "add_issue_comment", {"issue_id": 42, "comment": "LGTM"},
    )


def test_issues_check():
    with patch("gateway.cli.client.call_tool", return_value={"status": "added", "id": 42, "item": "Write docs"}) as mock:
        r = runner.invoke(main, ["issues", "check", "42", "Write docs"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "add_checklist_item", {"issue_id": 42, "item": "Write docs"},
    )


def test_issues_toggle():
    with patch("gateway.cli.client.call_tool", return_value={"status": "toggled", "id": 42, "item": "Write docs", "done": True}) as mock:
        r = runner.invoke(main, ["issues", "toggle", "42", "Write docs"])
    assert r.exit_code == 0
    mock.assert_called_once_with(
        "http://127.0.0.1:4000/mcp", "toggle_checklist_item", {"issue_id": 42, "item_text": "Write docs"},
    )
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/cli/test_issues.py::test_issues_comment tests/cli/test_issues.py::test_issues_check tests/cli/test_issues.py::test_issues_toggle -v
```

Expected: `No such command 'comment'` etc.

- [ ] **Step 3: Add comment, check, toggle to gateway/cli/commands/issues.py**

Append to `gateway/cli/commands/issues.py`:

```python
@group.command("comment")
@click.argument("issue-id", type=int)
@click.argument("comment")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_comment(obj: dict, issue_id: int, comment: str, as_json: bool) -> None:
    """Add a comment to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_issue_comment", {"issue_id": issue_id, "comment": comment})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Comment added to #{issue_id}")


@group.command("check")
@click.argument("issue-id", type=int)
@click.argument("item")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_checklist_item(obj: dict, issue_id: int, item: str, as_json: bool) -> None:
    """Add a checklist item to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_checklist_item", {"issue_id": issue_id, "item": item})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Checklist item added to #{issue_id}")


@group.command("toggle")
@click.argument("issue-id", type=int)
@click.argument("item-text")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def toggle_checklist_item(obj: dict, issue_id: int, item_text: str, as_json: bool) -> None:
    """Toggle a checklist item done/undone."""
    try:
        data = client.call_tool(obj["server"], "toggle_checklist_item", {"issue_id": issue_id, "item_text": item_text})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Toggled '{ item_text}' on #{issue_id}")
```

- [ ] **Step 4: Run all CLI tests — expect pass**

```bash
uv run pytest tests/cli/test_issues.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/cli/commands/issues.py tests/cli/test_issues.py
git commit -m "feat: add gw issues comment, check, toggle CLI commands"
```

---

## Task 11: Wire main.py and config.py

**Files:**
- Modify: `gateway/main.py`
- Modify: `gateway/config.py`

- [ ] **Step 1: Update gateway/main.py — swap vikunja for issues**

Replace:
```python
from gateway.tools import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, vikunja
```
With:
```python
from gateway.tools import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, issues
```

Replace:
```python
    vikunja.init(config.vikunja)
    vikunja.register(mcp)
```
With:
```python
    issues.init(config.obsidian)
    issues.register(mcp)
```

- [ ] **Step 2: Update gateway/config.py — remove VikunjaConfig**

Remove the `VikunjaConfig` class and the `vikunja` field from `Config`. The final `config.py`:

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class IMAPConfig(BaseModel):
    host: str = "imap.mailbox.org"
    port: int = 993
    username: str = ""
    password: str = ""


class ObsidianConfig(BaseModel):
    vault_path: str = ""


class KarakeepConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""


class OwnTracksConfig(BaseModel):
    base_url: str = ""
    username: str = ""
    password: str = ""
    owntracks_user: str = ""
    owntracks_device: str = ""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4000


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    imap: IMAPConfig = IMAPConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    karakeep: KarakeepConfig = KarakeepConfig()
    owntracks: OwnTracksConfig = OwnTracksConfig()
    server: ServerConfig = ServerConfig()
```

- [ ] **Step 3: Run the server registration test**

```bash
uv run pytest tests/test_issues.py::test_issues_registered_in_server -v
```

Expected: PASS.

- [ ] **Step 4: Run all non-vikunja tests**

```bash
uv run pytest tests/ -v --ignore=tests/test_vikunja.py --ignore=tests/cli/test_vikunja.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/main.py gateway/config.py
git commit -m "feat: wire Obsidian issues into MCP server; remove VikunjaConfig"
```

---

## Task 12: Retire Vikunja files

**Files:**
- Delete: `gateway/tools/vikunja.py`
- Delete: `gateway/cli/commands/vikunja.py`
- Delete: `tests/test_vikunja.py`
- Delete: `tests/cli/test_vikunja.py`

- [ ] **Step 1: Delete the four Vikunja files**

```bash
git rm gateway/tools/vikunja.py gateway/cli/commands/vikunja.py tests/test_vikunja.py tests/cli/test_vikunja.py
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass, no import errors.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: retire Vikunja tool, CLI, and tests"
```

---

## Task 13: Obsidian templates

**Files:**
- Create: `<vault>/_templates/Issue.md`
- Create: `<vault>/_templates/Bases/Issues.md`

The vault path is in `GATEWAY_OBSIDIAN__VAULT_PATH` (or `.env`). Run these `gw notes create` commands after the gateway server is running, substituting the real vault path as needed.

- [ ] **Step 1: Create the issue note template**

```bash
gw notes create "_templates/Issue.md" "---
id: 
title: 
project: 
status: open
priority: 0
due: 
labels: []
reminders: []
related: []
---



## Checklist

- [ ] 

## Comments
"
```

Expected: `Created: _templates/Issue.md`

- [ ] **Step 2: Ensure Bases subfolder exists then create the Bases template**

```bash
gw notes create "_templates/Bases/Issues.md" "---
type: base
source: Projects/_issues
columns:
  - field: id
    label: '#'
  - field: title
  - field: project
  - field: status
  - field: priority
  - field: due
  - field: labels
filters: []
sort:
  - field: id
    order: asc
---
"
```

Expected: `Created: _templates/Bases/Issues.md`

Note: The Bases frontmatter format may need adjustment to match your Obsidian version. Open the file in Obsidian and use the Bases UI to configure columns/filters visually if the above schema doesn't match.

- [ ] **Step 3: Final full test run**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: add Obsidian issue and Bases view templates"
```
