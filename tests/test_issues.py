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
