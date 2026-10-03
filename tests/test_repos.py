from __future__ import annotations

import json

import pytest

import gateway.tools.repos as repos
from gateway.config import GitHubConfig


@pytest.fixture
def gh(github_repos_server, github_token):
    base_url, fake = github_repos_server
    repos.init(GitHubConfig(repo="awfulwoman/meta", token=github_token), api_url=base_url)
    return fake, github_token


def test_list_repos_skips_forks_and_archived(gh):
    fake, token = gh
    fake.seed(token, "gateway", description="MCP server", topics=["mcp"])
    fake.seed(token, "a-fork", fork=True)
    fake.seed(token, "old-thing", archived=True)

    result = json.loads(repos.list_repos())

    assert [r["name"] for r in result] == ["gateway"]
    assert result[0]["description"] == "MCP server"
    assert result[0]["topics"] == ["mcp"]


def test_list_repos_follows_pagination(gh):
    fake, token = gh
    for i in range(130):
        fake.seed(token, f"repo-{i:03d}")

    result = json.loads(repos.list_repos())

    assert len(result) == 130


def test_get_repo_overview_returns_docs_commits_and_open_issues(gh):
    fake, token = gh
    fake.seed(
        token, "wiki-compiler", description="Compiles a wiki", private=True,
        readme="# wiki-compiler\nCompiles sources.", claude_md="Use TDD.",
        commits=[
            {"commit": {"message": "Add synthesis\n\nLonger body", "committer": {"date": "2026-10-03T10:00:00Z"}}},
            {"commit": {"message": "Fix index casing", "committer": {"date": "2026-10-02T09:00:00Z"}}},
        ],
        issues=[
            {"number": 1, "title": "PRD: compile personal sources", "state": "open"},
            {"number": 2, "title": "A pull request", "state": "open", "pull_request": {"url": "x"}},
            {"number": 3, "title": "Done thing", "state": "closed"},
        ],
    )

    result = json.loads(repos.get_repo_overview("wiki-compiler"))

    assert result["name"] == "wiki-compiler"
    assert result["private"] is True
    assert result["readme"].startswith("# wiki-compiler")
    assert result["claude_md"] == "Use TDD."
    assert result["recent_commits"] == [
        {"date": "2026-10-03", "message": "Add synthesis"},
        {"date": "2026-10-02", "message": "Fix index casing"},
    ]
    assert result["open_issues"] == [{"number": 1, "title": "PRD: compile personal sources"}]


def test_get_repo_overview_tolerates_missing_readme_and_claude_md(gh):
    fake, token = gh
    fake.seed(token, "bare")

    result = json.loads(repos.get_repo_overview("bare"))

    assert result["readme"] is None
    assert result["claude_md"] is None


def test_get_repo_overview_unknown_repo_is_an_error_not_a_crash(gh):
    result = json.loads(repos.get_repo_overview("does-not-exist"))

    assert "error" in result
