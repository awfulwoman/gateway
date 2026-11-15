"""View and control of Ansible Semaphore UI (the open-source project on camina),
for inspecting scheduled/failed Ansible runs.

Terminology note: the tool names use the generic CI vocabulary the rest of the
world uses, mapped onto Semaphore's own model:

    project  -> project
    workflow -> task template (the reusable definition of what runs)
    pipeline -> task (a single run of a template, with a status and output)
    job      -> task (a run is atomic: one template run is one job)

So ``pipeline_id`` and ``job_id`` are both a Semaphore *task* id, and a
"pipeline" has exactly one "job". The API is Bearer-token authenticated; the
token is a Semaphore API token, not the admin password.
"""
from __future__ import annotations

import json
import re

import httpx

from gateway.config import SemaphoreConfig

_config: SemaphoreConfig | None = None
_api: str = ""  # test override; production uses the config's base_url

# A deploy runs with the vault unlocked, so a failing task can print a secret
# into its log — and this module hands that log back as plain text, to a caller
# that will read every character of it. Ansible's `no_log` covers the tasks
# that remember to set it; these catch the rest.
#
# Deliberately conservative: nothing here keys off a bare long random string,
# because that would also eat commit SHAs and task ids, which are the parts of
# a log worth reading. It matches the two shapes a secret actually leaks in —
# a dumped vault/PEM blob, and a `key: value` pair whose key names it one.
_REDACTIONS: list[tuple[re.Pattern, object]] = [
    # Ansible Vault ciphertext, as `ansible-vault view` or a dumped var prints it.
    (
        re.compile(r"\$ANSIBLE_VAULT;[^\n]*\n(?:[0-9a-f]{1,80}\n)+", re.MULTILINE),
        "<redacted: ansible-vault>",
    ),
    # PEM private keys.
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "<redacted: private key>",
    ),
    # password: hunter2 / token=abc / "api_key": "..." / vault_foo=...
    # The key may sit inside a longer name (api_token, admin_password,
    # vault_..._secret), so snake_case either side is absorbed. Both runs are
    # bounded: an unbounded pair of star groups backtracks quadratically on a
    # long line that contains no key name at all, and logs are long.
    (
        re.compile(
            r"""(?ix)
            \b([a-z0-9_]{0,40}
               (?:password|passwd|secret|token|api[_-]?key|access[_-]?key
                 |private[_-]?key|client[_-]?secret|passphrase|vault)
               [a-z0-9_]{0,20})\b
            (\s*"?\s*[:=]\s*)("?)([^\s"',}]+)""",
        ),
        r"\1\2\3<redacted>",
    ),
]


def _redact(text: str) -> str:
    """Mask secrets in text this process is about to hand to a caller."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def init(config: SemaphoreConfig, api_url: str = "") -> None:
    global _config, _api
    _config = config
    _api = api_url.rstrip("/") if api_url else ""


def _cfg() -> SemaphoreConfig:
    assert _config and _config.token, (
        "Semaphore not configured — set GATEWAY_SEMAPHORE__TOKEN"
    )
    return _config


def _base_url() -> str:
    url = _api or (_config.base_url if _config else "")
    if not url:
        raise RuntimeError("Semaphore not configured — set GATEWAY_SEMAPHORE__BASE_URL")
    return url.rstrip("/")


def _client() -> httpx.Client:
    cfg = _cfg()  # assert the token first, so its message wins over the URL one
    return httpx.Client(
        base_url=_base_url(),
        headers={"Authorization": f"Bearer {cfg.token}"},
        timeout=30,
    )


def _error_detail(r: httpx.Response) -> str:
    try:
        body = r.json()
        return body.get("message") or body.get("error") or r.text
    except ValueError:
        return r.text


def _get(path: str) -> list | dict:
    with _client() as c:
        r = c.get(path)
        if r.status_code >= 400:
            raise RuntimeError(f"Semaphore API error {r.status_code}: {_error_detail(r)}")
        return r.json()


def _get_text(path: str) -> str:
    with _client() as c:
        r = c.get(path)
        if r.status_code >= 400:
            raise RuntimeError(f"Semaphore API error {r.status_code}: {_error_detail(r)}")
        return r.text


def _post(path: str, body: dict) -> list | dict | None:
    with _client() as c:
        r = c.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Semaphore API error {r.status_code}: {_error_detail(r)}")
        return None if r.status_code == 204 else r.json()


def _project(p: dict) -> dict:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "alert": p.get("alert"),
        "max_parallel_tasks": p.get("max_parallel_tasks"),
        "created": p.get("created"),
    }


def _template(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "playbook": t.get("playbook"),
        "description": t.get("description") or "",
        "app": t.get("app"),
        "git_branch": t.get("git_branch"),
    }


def _task(t: dict, full: bool = False) -> dict:
    result = {
        "id": t.get("id"),
        "template_id": t.get("template_id"),
        "status": t.get("status"),
        "playbook": t.get("playbook"),
        "message": t.get("message") or "",
        "git_branch": t.get("git_branch"),
    }
    if full:
        result.update({
            "environment": t.get("environment"),
            "arguments": t.get("arguments"),
            "params": t.get("params"),
            "artifacts": t.get("artifacts"),
        })
    return result


def projects_list() -> str:
    """List every Semaphore project, with its id, name, alert flag and creation time."""
    return json.dumps([_project(p) for p in _get("/api/projects")])


def projects_search(query: str) -> str:
    """Search projects by name (case-insensitive substring). Semaphore projects
    carry only a name — they have no repository URL or description — so this
    matches against the name."""
    q = query.lower()
    matches = [p for p in _get("/api/projects") if q in (p.get("name") or "").lower()]
    return json.dumps([_project(p) for p in matches])


def workflows_search(project_id: int, query: str = "") -> str:
    """List a project's task templates (the "workflows" — the reusable definitions
    of what runs), newest first. `query` optionally filters by template name."""
    templates = _get(f"/api/project/{project_id}/templates")
    if query:
        q = query.lower()
        templates = [t for t in templates if q in (t.get("name") or "").lower()]
    templates = sorted(templates, key=lambda t: t.get("id") or 0, reverse=True)
    return json.dumps([_template(t) for t in templates])


def pipelines_list(project_id: int, workflow_id: int) -> str:
    """List the runs ("pipelines") of one task template ("workflow"), newest first.
    Each run is a Semaphore task; runs are ordered by descending id (higher id is newer)."""
    tasks = _get(f"/api/project/{project_id}/tasks")
    runs = [t for t in tasks if t.get("template_id") == workflow_id]
    runs = sorted(runs, key=lambda t: t.get("id") or 0, reverse=True)
    return json.dumps([_task(t) for t in runs])


def pipeline_jobs(project_id: int, pipeline_id: int) -> str:
    """List the jobs of a run ("pipeline"). An Ansible Semaphore task is atomic —
    one template run is one job — so this returns that single task. `pipeline_id`
    is the Semaphore task id."""
    task = _get(f"/api/project/{project_id}/tasks/{pipeline_id}")
    return json.dumps([_task(task)])


def jobs_describe(project_id: int, job_id: int) -> str:
    """Describe a single task ("job"): status, playbook, environment, git branch,
    message, arguments and params. `job_id` is the Semaphore task id. Secrets in
    the arguments and params are masked."""
    task = _get(f"/api/project/{project_id}/tasks/{job_id}")
    detail = _task(task, full=True)
    for key in ("arguments", "params", "environment"):
        if isinstance(detail.get(key), str):
            detail[key] = _redact(detail[key])
    return json.dumps(detail)


def jobs_logs(project_id: int, job_id: int) -> str:
    """Fetch the raw log output of a task ("job") as plain text. `job_id` is the
    Semaphore task id. Secrets a failing task prints are masked, since a deploy
    runs with the vault unlocked."""
    text = _get_text(f"/api/project/{project_id}/tasks/{job_id}/raw_output")
    return json.dumps({"task_id": job_id, "output": _redact(text)})


def workflows_run(project_id: int, workflow_id: int, message: str = "",
                  git_branch: str = "", playbook: str = "", arguments: str = "",
                  dry_run: bool = False, diff: bool = False, debug: bool = False,
                  limit: str = "", environment: str = "", inventory_id: int = 0) -> str:
    """Start a run of a task template ("workflow"): queues a Semaphore task and
    returns it (its id is the new "pipeline"/"job" id). `workflow_id` is the
    template id. Optional overrides mirror Semaphore's task-start body; `arguments`
    is a JSON array string, e.g. '["--tags", "composition"]'."""
    body: dict = {"template_id": workflow_id}
    for key, value in (("message", message), ("git_branch", git_branch), ("playbook", playbook),
                       ("arguments", arguments), ("limit", limit), ("environment", environment)):
        if value:
            body[key] = value
    if inventory_id:
        body["inventory_id"] = inventory_id
    if dry_run:
        body["dry_run"] = True
    if diff:
        body["diff"] = True
    if debug:
        body["debug"] = True
    task = _post(f"/api/project/{project_id}/tasks", body)
    return json.dumps(_task(task, full=True))


def pipelines_stop(project_id: int, pipeline_id: int, force: bool = False) -> str:
    """Stop a running task ("pipeline"). `pipeline_id` is the Semaphore task id.
    `force` kills the task immediately instead of stopping it gracefully."""
    _post(f"/api/project/{project_id}/tasks/{pipeline_id}/stop", {"force": force})
    return json.dumps({"task_id": pipeline_id, "stopped": True})


def register(mcp) -> None:
    for fn in [projects_list, projects_search, workflows_search, pipelines_list,
               pipeline_jobs, jobs_describe, jobs_logs, workflows_run, pipelines_stop]:
        mcp.tool()(fn)
