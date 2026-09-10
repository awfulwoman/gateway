from __future__ import annotations
import json
import logging
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from gateway.auth import parse_clients
from gateway.usage import UsageLogMiddleware

CLIENTS = parse_clients(["laptop:secret1", "jarvis:secret2"])


async def _echo(request):
    body = await request.json()
    return JSONResponse({"echo": body})


async def _ok(request):
    return JSONResponse({"ok": True})


def _client() -> TestClient:
    app = Starlette(routes=[
        Route("/mcp", _echo, methods=["POST"]),
        Route("/mcp", _ok, methods=["GET"]),
        Route("/v1/reminders", _ok, methods=["GET"]),
        Route("/health", _ok, methods=["GET"]),
    ])
    return TestClient(UsageLogMiddleware(app, CLIENTS))


def _records(caplog) -> list[dict]:
    return [json.loads(r.message) for r in caplog.records if r.name == "gateway.usage"]


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger="gateway.usage")


def test_tools_call_logs_caller_tool_and_full_args(caplog):
    body = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "create_note", "arguments": {"path": "a.md", "content": "hello"}}}
    r = _client().post("/mcp", json=body, headers={"Authorization": "Bearer secret1"})
    assert r.status_code == 200

    (rec,) = _records(caplog)
    assert rec["caller"] == "laptop"
    assert rec["method"] == "tools/call"
    assert rec["tool"] == "create_note"
    assert rec["args"] == {"path": "a.md", "content": "hello"}
    assert rec["rpc_id"] == 7
    assert rec["status"] == 200
    assert "duration_ms" in rec and "ts" in rec


def test_body_is_replayed_intact_to_downstream(caplog):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "x", "arguments": {"k": "v"}}}
    r = _client().post("/mcp", json=body, headers={"Authorization": "Bearer secret1"})
    assert r.json() == {"echo": body}


def test_unknown_bearer_logs_caller_null(caplog):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    _client().post("/mcp", json=body, headers={"Authorization": "Bearer nope"})
    (rec,) = _records(caplog)
    assert rec["caller"] is None
    assert rec["method"] == "tools/list"
    assert rec["tool"] is None


def test_missing_auth_header_logs_caller_null(caplog):
    _client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    (rec,) = _records(caplog)
    assert rec["caller"] is None


def test_batch_body_emits_one_record_per_call(caplog):
    batch = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "a", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "b", "arguments": {"n": 1}}},
    ]
    _client().post("/mcp", json=batch, headers={"Authorization": "Bearer secret2"})
    recs = _records(caplog)
    assert [r["tool"] for r in recs] == ["a", "b"]
    assert all(r["caller"] == "jarvis" for r in recs)


def test_non_mcp_paths_are_not_logged(caplog):
    c = _client()
    assert c.get("/v1/reminders").status_code == 200
    assert c.get("/health").status_code == 200
    assert _records(caplog) == []


def test_get_mcp_with_no_body_still_logs_a_record(caplog):
    _client().get("/mcp", headers={"Authorization": "Bearer secret1"})
    (rec,) = _records(caplog)
    assert rec["caller"] == "laptop"
    assert rec["method"] is None


def test_forwarded_for_is_recorded(caplog):
    _client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                   headers={"Authorization": "Bearer secret1", "X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
    (rec,) = _records(caplog)
    assert rec["ip"] == "203.0.113.5"
