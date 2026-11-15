"""Ansible Semaphore UI tools, against an in-process fake (see `_FakeSemaphore`
in conftest). Field names in the seeded payloads follow Semaphore's OpenAPI
contract (Project, Template, Task)."""
from __future__ import annotations

import json

import pytest

import gateway.tools.semaphore as semaphore
from gateway.config import SemaphoreConfig

PROJECT_A = {"id": 1, "name": "infra", "alert": True, "max_parallel_tasks": 1, "created": "2026-01-01T00:00:00Z"}
PROJECT_B = {"id": 2, "name": "other", "alert": False, "max_parallel_tasks": 0, "created": "2026-02-01T00:00:00Z"}

TEMPLATE = {"id": 10, "name": "storage: core", "playbook": "playbooks/hosts/server-64gb-storage/core.yaml",
            "description": "Nightly storage run", "app": "ansible", "git_branch": "main"}


@pytest.fixture
def sem(semaphore_server, semaphore_token):
    base_url, fake = semaphore_server
    semaphore.init(SemaphoreConfig(token=semaphore_token), api_url=base_url)
    return fake, semaphore_token


# --- projects_list / projects_search -----------------------------------

def test_projects_list_returns_projects(sem):
    fake, token = sem
    fake.seed_project(token, PROJECT_A)
    fake.seed_project(token, PROJECT_B)

    result = json.loads(semaphore.projects_list())

    assert [p["name"] for p in result] == ["infra", "other"]
    assert result[0]["id"] == 1
    assert result[0]["alert"] is True


def test_projects_search_matches_name_case_insensitively(sem):
    fake, token = sem
    fake.seed_project(token, PROJECT_A)
    fake.seed_project(token, PROJECT_B)

    result = json.loads(semaphore.projects_search("INFRA"))

    assert [p["name"] for p in result] == ["infra"]


def test_projects_search_no_match(sem):
    fake, token = sem
    fake.seed_project(token, PROJECT_A)

    assert json.loads(semaphore.projects_search("nope")) == []


# --- workflows_search ---------------------------------------------------

def test_workflows_search_lists_templates_newest_first(sem):
    fake, token = sem
    fake.seed_template(token, {**TEMPLATE, "id": 10, "name": "older"})
    fake.seed_template(token, {**TEMPLATE, "id": 11, "name": "newer"})

    result = json.loads(semaphore.workflows_search(1))

    assert [t["name"] for t in result] == ["newer", "older"]
    assert result[0]["playbook"] == TEMPLATE["playbook"]


def test_workflows_search_filters_by_name(sem):
    fake, token = sem
    fake.seed_template(token, {**TEMPLATE, "id": 10, "name": "storage: core"})
    fake.seed_template(token, {**TEMPLATE, "id": 11, "name": "router: core"})

    result = json.loads(semaphore.workflows_search(1, query="storage"))

    assert [t["name"] for t in result] == ["storage: core"]


# --- pipelines_list / pipeline_jobs -------------------------------------

def _task(task_id, template_id, status, **extra):
    t = {"id": task_id, "template_id": template_id, "status": status,
         "playbook": TEMPLATE["playbook"], "message": "", "git_branch": "main"}
    t.update(extra)
    return t


def test_pipelines_list_filters_by_workflow_and_sorts_newest_first(sem):
    fake, token = sem
    fake.seed_task(token, _task(100, 10, "success"))
    fake.seed_task(token, _task(101, 10, "failed"))
    fake.seed_task(token, _task(102, 11, "success"))  # a different template

    result = json.loads(semaphore.pipelines_list(1, workflow_id=10))

    assert [t["id"] for t in result] == [101, 100]
    assert result[0]["status"] == "failed"


def test_pipeline_jobs_returns_the_single_atomic_task(sem):
    fake, token = sem
    fake.seed_task(token, _task(101, 10, "failed", message="host unreachable"))

    result = json.loads(semaphore.pipeline_jobs(1, pipeline_id=101))

    assert result == [{
        "id": 101, "template_id": 10, "status": "failed", "playbook": TEMPLATE["playbook"],
        "message": "host unreachable", "git_branch": "main",
    }]


# --- jobs_describe / jobs_logs ------------------------------------------

def test_jobs_describe_returns_full_detail(sem):
    fake, token = sem
    fake.seed_task(token, _task(101, 10, "failed", environment="{}", arguments='["--limit", "server-64gb-storage"]'))

    result = json.loads(semaphore.jobs_describe(1, job_id=101))

    assert result["id"] == 101
    assert result["status"] == "failed"
    assert result["arguments"] == '["--limit", "server-64gb-storage"]'


def test_jobs_logs_returns_raw_output(sem):
    fake, token = sem
    fake.seed_task(token, _task(101, 10, "failed"), output="PLAY RECAP\nok=3 changed=1 failed=1\n")

    result = json.loads(semaphore.jobs_logs(1, job_id=101))

    assert result["task_id"] == 101
    assert "failed=1" in result["output"]


# --- workflows_run / pipelines_stop -------------------------------------

def test_workflows_run_queues_a_task_with_minimal_body(sem):
    fake, token = sem
    result = json.loads(semaphore.workflows_run(1, workflow_id=10))

    assert result["template_id"] == 10
    assert result["status"] == "waiting"
    assert fake._token_db(token)["runs"] == [{"template_id": 10}]


def test_workflows_run_passes_overrides(sem):
    fake, token = sem
    semaphore.workflows_run(
        1, workflow_id=10, message="retry storage", git_branch="main",
        arguments='["--tags", "composition"]', dry_run=True, debug=True,
        limit="server-64gb-storage", environment="{}", inventory_id=7,
    )

    assert fake._token_db(token)["runs"][-1] == {
        "template_id": 10, "message": "retry storage", "git_branch": "main",
        "arguments": '["--tags", "composition"]', "dry_run": True, "debug": True,
        "limit": "server-64gb-storage", "environment": "{}", "inventory_id": 7,
    }


def test_pipelines_stop_posts_stop(sem):
    fake, token = sem
    result = json.loads(semaphore.pipelines_stop(1, pipeline_id=101))

    assert result == {"task_id": 101, "stopped": True}
    assert fake._token_db(token)["stops"] == [{"task_id": 101, "force": False}]


def test_pipelines_stop_with_force(sem):
    fake, token = sem
    semaphore.pipelines_stop(1, pipeline_id=101, force=True)

    assert fake._token_db(token)["stops"] == [{"task_id": 101, "force": True}]


# --- errors -------------------------------------------------------------

def test_unknown_task_raises_with_semaphores_message(sem):
    with pytest.raises(RuntimeError, match="404"):
        semaphore.jobs_describe(1, job_id=999)


def test_unconfigured_token_raises_a_helpful_error():
    semaphore.init(SemaphoreConfig())
    with pytest.raises(AssertionError, match="GATEWAY_SEMAPHORE__TOKEN"):
        semaphore.projects_list()


def test_missing_base_url_raises_a_helpful_error():
    semaphore.init(SemaphoreConfig(token="x"), api_url="")
    with pytest.raises(RuntimeError, match="GATEWAY_SEMAPHORE__BASE_URL"):
        semaphore.projects_list()


# --- registration -------------------------------------------------------

async def test_server_registers_the_semaphore_tools():
    from gateway.config import Config
    from gateway.main import create_server
    names = {t.name for t in await create_server(Config(_env_file=None)).list_tools()}
    assert {"projects_list", "projects_search", "workflows_search", "pipelines_list",
            "pipeline_jobs", "jobs_describe", "jobs_logs", "workflows_run",
            "pipelines_stop"} <= names
