from __future__ import annotations
import json
from pathlib import Path
import pytest
import gateway.tools.issues as issues
from gateway.config import ObsidianConfig

PROJECT = "Software/TestProject"

SAMPLE = """\
---
id: 42
title: Fix login bug
project: Software/TestProject
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


def _make_issues_dir(vault: Path, project: str = PROJECT) -> Path:
    d = vault / "Projects" / project / "_issues"
    d.mkdir(parents=True)
    return d


def test_slugify_basic():
    assert issues._slugify("Fix login bug") == "fix-login-bug"


def test_slugify_special_chars():
    assert issues._slugify("Can't connect to DB!") == "cant-connect-to-db"


def test_slugify_long_title():
    assert len(issues._slugify("a" * 100)) <= 60


def test_slugify_empty_result():
    assert issues._slugify("!!!!") == "issue"


def test_next_id_empty(vault):
    assert issues._next_id() == 1


def test_next_id_increments(vault):
    d = _make_issues_dir(vault)
    (d / "0001-first.md").write_text("")
    (d / "0003-third.md").write_text("")
    assert issues._next_id() == 4


def test_next_id_across_projects(vault):
    d1 = _make_issues_dir(vault, "Software/Alpha")
    d2 = _make_issues_dir(vault, "Homelab/Beta")
    (d1 / "0001-a.md").write_text("")
    (d2 / "0005-b.md").write_text("")
    assert issues._next_id() == 6


def test_find_file(vault):
    d = _make_issues_dir(vault)
    f = d / "0042-test.md"
    f.write_text("x")
    assert issues._find_file(42) == f


def test_find_file_across_projects(vault):
    d1 = _make_issues_dir(vault, "Software/Alpha")
    d2 = _make_issues_dir(vault, "Homelab/Beta")
    (d1 / "0001-a.md").write_text("x")
    f = d2 / "0002-b.md"
    f.write_text("x")
    assert issues._find_file(2) == f


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
        "id": 1, "title": "Test issue", "project": "Software/TestProject",
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


def test_list_issues_empty(vault):
    result = json.loads(issues.list_issues())
    assert result == []


def test_list_issues_returns_summary(vault):
    d = _make_issues_dir(vault)
    (d / "0001-test.md").write_text(
        f"---\nid: 1\ntitle: Test\nproject: {PROJECT}\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n"
    )
    result = json.loads(issues.list_issues())
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["title"] == "Test"
    assert result[0]["project"] == PROJECT
    assert "checklist" not in result[0]
    assert "comments" not in result[0]


def test_list_issues_filter_project(vault):
    d1 = _make_issues_dir(vault, "Software/Alpha")
    d2 = _make_issues_dir(vault, "Software/Beta")
    (d1 / "0001-alpha.md").write_text("---\nid: 1\ntitle: A\nproject: Software/Alpha\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    (d2 / "0002-beta.md").write_text("---\nid: 2\ntitle: B\nproject: Software/Beta\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    result = json.loads(issues.list_issues(project="Software/Alpha"))
    assert len(result) == 1
    assert result[0]["title"] == "A"


def test_list_issues_filter_status(vault):
    d = _make_issues_dir(vault)
    (d / "0001-open.md").write_text(f"---\nid: 1\ntitle: Open\nproject: {PROJECT}\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    (d / "0002-done.md").write_text(f"---\nid: 2\ntitle: Done\nproject: {PROJECT}\nstatus: done\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    result = json.loads(issues.list_issues(status="open"))
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_list_issues_sorted_by_id(vault):
    d1 = _make_issues_dir(vault, "Software/Alpha")
    d2 = _make_issues_dir(vault, "Homelab/Beta")
    (d2 / "0002-b.md").write_text("---\nid: 2\ntitle: B\nproject: Homelab/Beta\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    (d1 / "0001-a.md").write_text("---\nid: 1\ntitle: A\nproject: Software/Alpha\nstatus: open\npriority: 0\n---\n\n## Checklist\n\n## Comments\n")
    result = json.loads(issues.list_issues())
    assert [r["id"] for r in result] == [1, 2]


def test_get_issue_not_found(vault):
    result = json.loads(issues.get_issue(99))
    assert "error" in result


def test_get_issue_full_detail(vault):
    d = _make_issues_dir(vault)
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


def test_create_requires_project(vault):
    result = json.loads(issues.create_issue("No project"))
    assert "error" in result


def test_create_assigns_id_1_when_empty(vault):
    result = json.loads(issues.create_issue("First issue", project=PROJECT))
    assert result["id"] == 1


def test_create_filename_format(vault):
    result = json.loads(issues.create_issue("Fix Login Bug", project=PROJECT))
    path = vault / result["path"]
    assert path.exists()
    assert path.name == "0001-fix-login-bug.md"
    assert path.parent == vault / "Projects" / PROJECT / "_issues"


def test_create_sequential_ids(vault):
    issues.create_issue("First", project=PROJECT)
    issues.create_issue("Second", project=PROJECT)
    issues.create_issue("Third", project=PROJECT)
    r = json.loads(issues.get_issue(3))
    assert r["id"] == 3
    assert r["title"] == "Third"


def test_create_sequential_ids_across_projects(vault):
    issues.create_issue("First", project="Software/Alpha")
    issues.create_issue("Second", project="Homelab/Beta")
    r = json.loads(issues.get_issue(2))
    assert r["id"] == 2
    assert r["title"] == "Second"


def test_create_stores_all_fields(vault):
    issues.create_issue(
        "My issue",
        project=PROJECT,
        description="Details here",
        due="2026-07-01",
        priority=2,
        labels=["bug", "urgent"],
        reminders=["2026-06-30T09:00:00Z"],
        related=[5],
        checklist_items=["Step 1", "Step 2"],
    )
    result = json.loads(issues.get_issue(1))
    assert result["project"] == PROJECT
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
    issues.create_issue("Issue", project=PROJECT)
    result = json.loads(issues.get_issue(1))
    assert result["status"] == "open"


def test_update_title(vault):
    issues.create_issue("Original", project=PROJECT)
    issues.update_issue(1, title="Updated")
    assert json.loads(issues.get_issue(1))["title"] == "Updated"


def test_update_status(vault):
    issues.create_issue("Issue", project=PROJECT)
    issues.update_issue(1, status="in-progress")
    assert json.loads(issues.get_issue(1))["status"] == "in-progress"


def test_update_not_found(vault):
    result = json.loads(issues.update_issue(99, title="x"))
    assert "error" in result


def test_update_invalid_status(vault):
    issues.create_issue("Issue", project=PROJECT)
    result = json.loads(issues.update_issue(1, status="closed"))
    assert "error" in result


def test_delete_issue(vault):
    issues.create_issue("To delete", project=PROJECT)
    issues.delete_issue(1)
    result = json.loads(issues.get_issue(1))
    assert "error" in result


def test_delete_not_found(vault):
    result = json.loads(issues.delete_issue(99))
    assert "error" in result


def test_add_comment(vault):
    issues.create_issue("Issue", project=PROJECT)
    issues.add_issue_comment(1, "First comment")
    result = json.loads(issues.get_issue(1))
    assert len(result["comments"]) == 1
    assert result["comments"][0]["text"] == "First comment"


def test_add_comment_appends(vault):
    issues.create_issue("Issue", project=PROJECT)
    issues.add_issue_comment(1, "Comment A")
    issues.add_issue_comment(1, "Comment B")
    result = json.loads(issues.get_issue(1))
    assert len(result["comments"]) == 2
    assert result["comments"][1]["text"] == "Comment B"


def test_add_checklist_item(vault):
    issues.create_issue("Issue", project=PROJECT)
    issues.add_checklist_item(1, "New task")
    result = json.loads(issues.get_issue(1))
    assert any(c["text"] == "New task" for c in result["checklist"])
    assert result["checklist"][-1]["done"] is False


def test_toggle_checklist_item_to_done(vault):
    issues.create_issue("Issue", project=PROJECT, checklist_items=["Do thing"])
    issues.toggle_checklist_item(1, "Do thing")
    result = json.loads(issues.get_issue(1))
    assert result["checklist"][0]["done"] is True


def test_toggle_checklist_item_back_to_undone(vault):
    issues.create_issue("Issue", project=PROJECT, checklist_items=["Do thing"])
    issues.toggle_checklist_item(1, "Do thing")
    issues.toggle_checklist_item(1, "Do thing")
    result = json.loads(issues.get_issue(1))
    assert result["checklist"][0]["done"] is False


def test_toggle_checklist_item_not_found(vault):
    issues.create_issue("Issue", project=PROJECT)
    result = json.loads(issues.toggle_checklist_item(1, "Nonexistent"))
    assert "error" in result


def test_update_preserves_checklist_and_comments(vault):
    issues.create_issue("Issue", project=PROJECT, checklist_items=["Step 1"])
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
