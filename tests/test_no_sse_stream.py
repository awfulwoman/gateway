from __future__ import annotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from gateway.main import NoSseStreamMiddleware


async def _ok(request):
    return JSONResponse({"ok": True})


def _client() -> TestClient:
    app = Starlette(routes=[
        Route("/mcp", _ok, methods=["GET", "POST"]),
        Route("/v1/thing", _ok, methods=["GET"]),
    ])
    return TestClient(NoSseStreamMiddleware(app))


def test_get_mcp_returns_405_with_allow_post():
    r = _client().get("/mcp")
    assert r.status_code == 405
    assert r.headers["allow"] == "POST"


def test_post_mcp_passes_through():
    assert _client().post("/mcp").status_code == 200


def test_get_other_path_passes_through():
    assert _client().get("/v1/thing").status_code == 200


async def test_non_http_scope_passes_through():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    await NoSseStreamMiddleware(app)({"type": "lifespan"}, None, None)
    assert calls == ["lifespan"]
