"""Read-only view of the owner's GitHub repositories: what each one is, how
active it is, and what's open on it. Reuses the issues tool's token
(GitHubConfig) and derives the owner from its `repo` setting.

Raw media type for README/CLAUDE.md so the API returns plain text rather than
base64-wrapped JSON.
"""
from __future__ import annotations

import json

import httpx

from gateway.config import GitHubConfig

_config: GitHubConfig | None = None
_api: str = "https://api.github.com"
_PER_PAGE = 100


def init(config: GitHubConfig, api_url: str = "https://api.github.com") -> None:
    global _config, _api
    _config = config
    _api = api_url.rstrip("/")


def _cfg() -> GitHubConfig:
    assert _config and _config.repo and _config.token, (
        "repos not configured — set GATEWAY_GITHUB__REPO and GATEWAY_GITHUB__TOKEN"
    )
    return _config


def _owner() -> str:
    return _cfg().repo.split("/")[0]


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_api,
        headers={"Authorization": f"Bearer {_cfg().token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )


def _summary(r: dict) -> dict:
    return {
        "name": r.get("name"),
        "description": r.get("description") or "",
        "private": r.get("private"),
        "pushed_at": r.get("pushed_at"),
        "topics": r.get("topics") or [],
    }


def _raw(c: httpx.Client, path: str) -> str | None:
    r = c.get(path, headers={"Accept": "application/vnd.github.raw+json"})
    return r.text if r.status_code == 200 else None


def list_repos() -> str:
    """List the owner's own repositories (no forks, no archived), with description, topics and last push date."""
    repos: list[dict] = []
    with _client() as c:
        page = 1
        while True:
            r = c.get("/user/repos", params={"affiliation": "owner", "per_page": _PER_PAGE, "page": page})
            r.raise_for_status()
            batch = r.json()
            repos += [_summary(x) for x in batch if not x.get("fork") and not x.get("archived")]
            if len(batch) < _PER_PAGE:
                break
            page += 1
    return json.dumps(repos)


def get_repo_overview(repo: str) -> str:
    """Overview of one of the owner's repositories: description, README, CLAUDE.md, the last 20 commits and open issues."""
    base = f"/repos/{_owner()}/{repo}"
    with _client() as c:
        meta = c.get(base)
        if meta.status_code != 200:
            return json.dumps({"error": f"Repository not found: {repo}"})
        commits = c.get(f"{base}/commits", params={"per_page": 20})
        issues = c.get(f"{base}/issues", params={"state": "open", "per_page": 50})
        result = _summary(meta.json()) | {
            "readme": _raw(c, f"{base}/readme"),
            "claude_md": _raw(c, f"{base}/contents/CLAUDE.md"),
            "recent_commits": [
                {"date": x["commit"]["committer"]["date"][:10], "message": x["commit"]["message"].splitlines()[0]}
                for x in (commits.json() if commits.status_code == 200 else [])
            ],
            "open_issues": [
                {"number": x["number"], "title": x["title"]}
                for x in (issues.json() if issues.status_code == 200 else [])
                if "pull_request" not in x
            ],
        }
    return json.dumps(result)


def register(mcp) -> None:
    for fn in [list_repos, get_repo_overview]:
        mcp.tool()(fn)
