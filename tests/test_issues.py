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
