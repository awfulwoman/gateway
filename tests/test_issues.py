from __future__ import annotations
import json
import re
from urllib.parse import unquote
import pytest
import gateway.tools.issues as issues
from gateway.config import GitHubConfig

REPO = "awfulwoman/meta"
SEED_LABELS = {"bug", "enhancement", "question", "area:infra", "area:process", "area:security"}


# --- fake GitHub REST API ----------------------------------------------

class FakeResp:
    def __init__(self, status_code: int, data=None, headers: dict | None = None):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}

    def json(self):
        if self._data is None:
            raise ValueError("no json body")
        return self._data

    @property
    def content(self) -> bytes:
        return b"x" if self._data is not None else b""

    @property
    def text(self) -> str:
        return json.dumps(self._data) if self._data is not None else ""


class FakeGitHub:
    """In-memory stand-in for the slice of the GitHub API the tools call.
    Monkeypatched in as issues._client(); acts as its own context manager."""

    def __init__(self):
        self.issues: dict[int, dict] = {}
        self.comments: dict[int, list] = {}
        self.repo_labels: set[str] = set(SEED_LABELS)
        self.label_posts: list[str] = []
        self.next = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @staticmethod
    def _path(url: str) -> str:
        return url.replace("https://api.github.com", "")

    def get(self, url: str, params: dict | None = None) -> FakeResp:
        path = self._path(url)
        base = f"/repos/{REPO}/issues"

        if path == base:
            state = (params or {}).get("state", "all")
            labels = (params or {}).get("labels")
            rows = []
            for iss in self.issues.values():
                if state != "all" and iss["state"] != state:
                    continue
                if labels and labels not in [l["name"] for l in iss["labels"]]:
                    continue
                rows.append(dict(iss))
            rows.sort(key=lambda i: i["number"])
            return FakeResp(200, rows)

        m = re.fullmatch(rf"{re.escape(base)}/(\d+)", path)
        if m:
            iss = self.issues.get(int(m.group(1)))
            return FakeResp(200, dict(iss)) if iss else FakeResp(404, {"message": "Not Found"})

        m = re.fullmatch(rf"{re.escape(base)}/(\d+)/comments", path)
        if m:
            return FakeResp(200, list(self.comments.get(int(m.group(1)), [])))

        m = re.fullmatch(rf"/repos/{re.escape(REPO)}/labels/(.+)", path)
        if m:
            name = unquote(m.group(1))
            if name in self.repo_labels:
                return FakeResp(200, {"name": name})
            return FakeResp(404, {"message": "Not Found"})

        raise AssertionError(f"unhandled GET {path}")

    def _reject_unknown_labels(self, names: list[str]) -> FakeResp | None:
        missing = [n for n in names if n not in self.repo_labels]
        if missing:
            return FakeResp(422, {"message": f"Validation Failed: unknown label(s) {missing}"})
        return None

    def post(self, url: str, json: dict | None = None) -> FakeResp:
        path = self._path(url)
        base = f"/repos/{REPO}/issues"
        body = json or {}

        if path == base:
            rejected = self._reject_unknown_labels(body.get("labels", []))
            if rejected:
                return rejected
            n = self.next
            self.next += 1
            iss = {
                "number": n,
                "title": body["title"],
                "body": body.get("body", ""),
                "state": "open",
                "node_id": f"I_kwDO_{n}",
                "labels": [{"name": l} for l in body.get("labels", [])],
                "html_url": f"https://github.com/{REPO}/issues/{n}",
            }
            self.issues[n] = iss
            return FakeResp(201, dict(iss))

        if path == f"/repos/{REPO}/labels":
            self.repo_labels.add(body["name"])
            self.label_posts.append(body["name"])
            return FakeResp(201, {"name": body["name"]})

        m = re.fullmatch(rf"{re.escape(base)}/(\d+)/comments", path)
        if m:
            n = int(m.group(1))
            c = {
                "body": body["body"],
                "created_at": "2026-08-30T13:00:00Z",
                "user": {"login": "awfulwoman"},
            }
            self.comments.setdefault(n, []).append(c)
            return FakeResp(201, dict(c))

        if path == "/graphql":
            if "deleteIssue" in body.get("query", ""):
                node_id = body["variables"]["id"]
                for k, v in list(self.issues.items()):
                    if v["node_id"] == node_id:
                        del self.issues[k]
                        return FakeResp(200, {"data": {"deleteIssue": {"clientMutationId": None}}})
                return FakeResp(200, {"errors": [{"message": "Could not resolve to a node"}]})

        raise AssertionError(f"unhandled POST {path}")

    def patch(self, url: str, json: dict | None = None) -> FakeResp:
        path = self._path(url)
        body = json or {}
        m = re.fullmatch(rf"/repos/{re.escape(REPO)}/issues/(\d+)", path)
        if not m:
            raise AssertionError(f"unhandled PATCH {path}")
        iss = self.issues.get(int(m.group(1)))
        if not iss:
            return FakeResp(404, {"message": "Not Found"})
        if "labels" in body:
            rejected = self._reject_unknown_labels(body["labels"])
            if rejected:
                return rejected
        if "title" in body:
            iss["title"] = body["title"]
        if "body" in body:
            iss["body"] = body["body"]
        if "state" in body:
            iss["state"] = body["state"]
        if "labels" in body:
            iss["labels"] = [{"name": l} for l in body["labels"]]
        return FakeResp(200, dict(iss))


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    issues.init(GitHubConfig(repo=REPO, token="test-token"))
    monkeypatch.setattr(issues, "_client", lambda: fake)
    return fake


# --- transport helpers -------------------------------------------------

def test_next_link_finds_next():
    header = (
        '<https://api.github.com/repositories/1/issues?page=2&per_page=100>; rel="next", '
        '<https://api.github.com/repositories/1/issues?page=9&per_page=100>; rel="last"'
    )
    assert issues._next_link(header) == "https://api.github.com/repositories/1/issues?page=2&per_page=100"


def test_next_link_absent():
    assert issues._next_link("") is None
    assert issues._next_link('<https://x/issues?page=9>; rel="last"') is None


def test_project_slug():
    assert issues._project_slug("Software/Podderton") == "podderton"
    assert issues._project_slug("Homelab/Beta") == "beta"
    assert issues._project_slug("Solo") == "solo"
    assert issues._project_slug("Nested/Path/My Project") == "my-project"
    assert issues._project_slug("") == "project"


def test_project_label():
    assert issues._project_label("Software/Podderton") == "project: podderton"


# --- body <-> fields ----------------------------------------------------

def test_render_body_description_only():
    body = issues._render_body("Just prose.", [], {})
    assert body == "Just prose.\n"
    assert "gateway:issue" not in body
    assert "## Checklist" not in body


def test_render_body_with_checklist_and_meta():
    body = issues._render_body(
        "Prose.",
        [{"text": "a", "done": False}, {"text": "b", "done": True}],
        {"priority": 2, "due": "2026-09-10"},
    )
    assert "## Checklist" in body
    assert "- [ ] a" in body
    assert "- [x] b" in body
    assert "<!-- gateway:issue" in body
    assert body.rstrip().endswith("-->")


def test_render_body_drops_empty_meta_values():
    body = issues._render_body("x", [], {"priority": 0, "due": "", "related": [], "project": "P"})
    assert "project: P" in body
    assert "priority" not in body
    assert "due" not in body


def test_parse_body_roundtrip():
    original_meta = {
        "priority": 3,
        "due": "2026-07-01",
        "project": "Software/Podderton",
        "related": [1, 5],
        "reminders": ["2026-06-30T09:00"],
    }
    checklist = [{"text": "Do thing", "done": False}, {"text": "Done thing", "done": True}]
    body = issues._render_body("Description here.", checklist, original_meta)

    desc, checks, meta = issues._parse_body(body)
    assert desc == "Description here."
    assert checks == checklist
    assert meta == original_meta


def test_parse_body_no_meta_no_checklist():
    desc, checks, meta = issues._parse_body("Plain body text.\n")
    assert desc == "Plain body text."
    assert checks == []
    assert meta == {}


def test_split_meta_handles_crlf():
    body = "Text.\r\n\r\n<!-- gateway:issue\r\npriority: 1\r\n-->\r\n"
    text, meta = issues._split_meta(body)
    assert text == "Text."
    assert meta == {"priority": 1}


def test_split_checklist_stops_at_next_heading():
    text = "Desc.\n\n## Checklist\n\n- [ ] a\n- [x] b\n\n## Notes\n\n- [ ] not a task\n"
    desc, checklist = issues._split_checklist(text)
    assert desc == "Desc."
    assert checklist == [{"text": "a", "done": False}, {"text": "b", "done": True}]


def test_status_of():
    assert issues._status_of("open", {}) == "open"
    assert issues._status_of("open", {"status": "in-progress"}) == "in-progress"
    assert issues._status_of("closed", {"status": "in-progress"}) == "done"


# --- create ------------------------------------------------------------

def test_create_returns_number_and_url(gh):
    result = json.loads(issues.create_issue("Fix login bug"))
    assert result["id"] == 1
    assert result["title"] == "Fix login bug"
    assert result["url"].endswith("/issues/1")


def test_create_sequential_numbers(gh):
    issues.create_issue("First")
    issues.create_issue("Second")
    assert json.loads(issues.get_issue(2))["title"] == "Second"


def test_create_stores_all_fields(gh):
    issues.create_issue(
        "My issue",
        project="Software/Podderton",
        description="Details here",
        due="2026-07-01",
        priority=2,
        labels=["bug"],
        reminders=["2026-06-30T09:00"],
        related=[5],
        checklist_items=["Step 1", "Step 2"],
    )
    r = json.loads(issues.get_issue(1))
    assert r["project"] == "Software/Podderton"
    assert r["description"] == "Details here"
    assert r["due"] == "2026-07-01"
    assert r["priority"] == 2
    assert r["labels"] == ["bug"]
    assert r["related"] == [5]
    assert r["reminders"] == ["2026-06-30T09:00"]
    assert r["checklist"] == [
        {"text": "Step 1", "done": False},
        {"text": "Step 2", "done": False},
    ]


def test_create_status_defaults_to_open(gh):
    issues.create_issue("Issue")
    assert json.loads(issues.get_issue(1))["status"] == "open"


def test_create_no_project_is_fine(gh):
    result = json.loads(issues.create_issue("No project needed"))
    assert result["id"] == 1


def test_create_passes_labels(gh):
    issues.create_issue("Labelled", labels=["area:infra", "enhancement"])
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"area:infra", "enhancement"}


# --- list ------------------------------------------------------------

def test_list_empty(gh):
    assert json.loads(issues.list_issues()) == []


def test_list_returns_summary_without_detail(gh):
    issues.create_issue("Issue", checklist_items=["a"])
    issues.add_issue_comment(1, "hi")
    rows = json.loads(issues.list_issues())
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert "checklist" not in rows[0]
    assert "comments" not in rows[0]


def test_list_skips_pull_requests(gh):
    issues.create_issue("Real issue")
    gh.issues[99] = {
        "number": 99, "title": "a PR", "body": "", "state": "open",
        "labels": [], "pull_request": {"url": "..."}, "node_id": "PR_1",
    }
    rows = json.loads(issues.list_issues())
    assert [r["id"] for r in rows] == [1]


def test_list_filter_project(gh):
    issues.create_issue("A", project="Software/Alpha")
    issues.create_issue("B", project="Software/Beta")
    rows = json.loads(issues.list_issues(project="Software/Alpha"))
    assert [r["title"] for r in rows] == ["A"]


def test_list_filter_status(gh):
    issues.create_issue("Open one")
    issues.create_issue("Done one")
    issues.update_issue(2, status="done")
    rows = json.loads(issues.list_issues(status="open"))
    assert [r["id"] for r in rows] == [1]
    rows = json.loads(issues.list_issues(status="done"))
    assert [r["id"] for r in rows] == [2]


def test_list_filter_in_progress(gh):
    issues.create_issue("One")
    issues.create_issue("Two")
    issues.update_issue(2, status="in-progress")
    rows = json.loads(issues.list_issues(status="in-progress"))
    assert [r["id"] for r in rows] == [2]


def test_list_filter_priority(gh):
    issues.create_issue("Low", priority=1)
    issues.create_issue("High", priority=3)
    rows = json.loads(issues.list_issues(priority=3))
    assert [r["title"] for r in rows] == ["High"]


def test_list_filter_label(gh):
    issues.create_issue("Tagged", labels=["bug"])
    issues.create_issue("Untagged")
    rows = json.loads(issues.list_issues(label="bug"))
    assert [r["title"] for r in rows] == ["Tagged"]


def test_list_sorted_by_id(gh):
    issues.create_issue("First")
    issues.create_issue("Second")
    rows = json.loads(issues.list_issues())
    assert [r["id"] for r in rows] == [1, 2]


# --- get ------------------------------------------------------------

def test_get_not_found(gh):
    assert "error" in json.loads(issues.get_issue(99))


def test_get_full_detail_with_comments(gh):
    issues.create_issue("Issue", description="Prose.", checklist_items=["step"])
    issues.add_issue_comment(1, "First comment")
    r = json.loads(issues.get_issue(1))
    assert r["id"] == 1
    assert r["description"] == "Prose."
    assert r["checklist"] == [{"text": "step", "done": False}]
    assert len(r["comments"]) == 1
    assert r["comments"][0]["text"] == "First comment"
    assert r["comments"][0]["author"] == "awfulwoman"
    assert r["comments"][0]["timestamp"] == "2026-08-30T13:00"


# --- update ------------------------------------------------------------

def test_update_title(gh):
    issues.create_issue("Original")
    issues.update_issue(1, title="Updated")
    assert json.loads(issues.get_issue(1))["title"] == "Updated"


def test_update_status_in_progress_keeps_issue_open(gh):
    issues.create_issue("Issue")
    issues.update_issue(1, status="in-progress")
    assert gh.issues[1]["state"] == "open"
    assert json.loads(issues.get_issue(1))["status"] == "in-progress"


def test_update_status_done_closes_issue(gh):
    issues.create_issue("Issue")
    issues.update_issue(1, status="done")
    assert gh.issues[1]["state"] == "closed"
    assert json.loads(issues.get_issue(1))["status"] == "done"


def test_update_status_open_reopens_and_clears_in_progress(gh):
    issues.create_issue("Issue")
    issues.update_issue(1, status="in-progress")
    issues.update_issue(1, status="done")
    issues.update_issue(1, status="open")
    assert gh.issues[1]["state"] == "open"
    assert json.loads(issues.get_issue(1))["status"] == "open"


def test_update_invalid_status(gh):
    issues.create_issue("Issue")
    assert "error" in json.loads(issues.update_issue(1, status="closed"))


def test_update_not_found(gh):
    assert "error" in json.loads(issues.update_issue(99, title="x"))


def test_update_preserves_checklist(gh):
    issues.create_issue("Issue", checklist_items=["Step 1"], description="Desc.")
    issues.update_issue(1, priority=4)
    r = json.loads(issues.get_issue(1))
    assert r["checklist"] == [{"text": "Step 1", "done": False}]
    assert r["description"] == "Desc."
    assert r["priority"] == 4


def test_update_replaces_labels(gh):
    issues.create_issue("Issue", labels=["bug", "area:infra"])
    issues.update_issue(1, labels=["area:infra", "enhancement"])
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"area:infra", "enhancement"}


# --- delete / comment / checklist ------------------------------------

def test_delete(gh):
    issues.create_issue("Doomed")
    issues.delete_issue(1)
    assert "error" in json.loads(issues.get_issue(1))


def test_delete_not_found(gh):
    assert "error" in json.loads(issues.delete_issue(99))


def test_add_comment(gh):
    issues.create_issue("Issue")
    out = json.loads(issues.add_issue_comment(1, "A comment"))
    assert out["status"] == "added"
    assert out["timestamp"] == "2026-08-30T13:00"
    assert json.loads(issues.get_issue(1))["comments"][0]["text"] == "A comment"


def test_add_checklist_item(gh):
    issues.create_issue("Issue")
    issues.add_checklist_item(1, "New task")
    r = json.loads(issues.get_issue(1))
    assert r["checklist"][-1] == {"text": "New task", "done": False}


def test_toggle_checklist_item(gh):
    issues.create_issue("Issue", checklist_items=["Do thing"])
    issues.toggle_checklist_item(1, "Do thing")
    assert json.loads(issues.get_issue(1))["checklist"][0]["done"] is True
    issues.toggle_checklist_item(1, "Do thing")
    assert json.loads(issues.get_issue(1))["checklist"][0]["done"] is False


def test_toggle_checklist_item_not_found(gh):
    issues.create_issue("Issue")
    assert "error" in json.loads(issues.toggle_checklist_item(1, "Nonexistent"))


# --- project link label --------------------------------------------

def test_create_with_project_adds_managed_label(gh):
    issues.create_issue("Issue", project="Software/Podderton")
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"project: podderton"}
    assert "project: podderton" in gh.repo_labels  # auto-created
    detail = json.loads(issues.get_issue(1))
    assert detail["labels"] == []  # managed label hidden from the tools' view
    assert detail["project"] == "Software/Podderton"


def test_create_project_label_coexists_with_other_labels(gh):
    issues.create_issue("Issue", project="Homelab/Beta", labels=["area:infra"])
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"area:infra", "project: beta"}
    assert json.loads(issues.get_issue(1))["labels"] == ["area:infra"]


def test_create_without_project_has_no_project_label(gh):
    issues.create_issue("Issue", labels=["bug"])
    assert all(not n.startswith("project: ") for n in [l["name"] for l in gh.issues[1]["labels"]])


def test_project_label_reuses_existing(gh):
    gh.repo_labels.add("project: podderton")
    issues.create_issue("Issue", project="Software/Podderton")
    assert gh.label_posts == []  # already present, not re-created


def test_update_set_project_adds_label(gh):
    issues.create_issue("Issue")
    issues.update_issue(1, project="Software/Podderton")
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"project: podderton"}
    assert json.loads(issues.get_issue(1))["project"] == "Software/Podderton"


def test_update_change_project_swaps_label(gh):
    issues.create_issue("Issue", project="Software/Alpha")
    issues.update_issue(1, project="Homelab/Beta")
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"project: beta"}


def test_update_labels_only_preserves_project_label(gh):
    issues.create_issue("Issue", project="Software/Podderton")
    issues.update_issue(1, labels=["area:process"])
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"area:process", "project: podderton"}


def test_update_strips_caller_supplied_project_label(gh):
    issues.create_issue("Issue", project="Software/Podderton")
    issues.update_issue(1, labels=["area:process", "project: bogus"])
    assert {l["name"] for l in gh.issues[1]["labels"]} == {"area:process", "project: podderton"}


def test_issues_registered_in_server():
    from gateway.config import Config
    from gateway import main as gw_main
    mcp = gw_main.create_server(Config())
    assert mcp is not None
