from __future__ import annotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from gateway.http_auth import BearerAuthMiddleware


async def _ok(request):
    return JSONResponse({"ok": True})


def _make_client(tokens: list[str], protect_prefix: str = "/mcp") -> TestClient:
    app = Starlette(routes=[
        Route("/mcp", _ok, methods=["GET"]),
        Route("/v1/reminders", _ok, methods=["GET"]),
    ])
    app = BearerAuthMiddleware(app, tokens, protect_prefix=protect_prefix)
    return TestClient(app)


def test_no_header_returns_401():
    client = _make_client(["good-token"])
    r = client.get("/mcp")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_wrong_token_returns_401():
    client = _make_client(["good-token"])
    r = client.get("/mcp", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_correct_token_passes_through():
    client = _make_client(["good-token"])
    r = client.get("/mcp", headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_any_of_multiple_tokens_is_accepted():
    client = _make_client(["token-a", "token-b"])
    r = client.get("/mcp", headers={"Authorization": "Bearer token-b"})
    assert r.status_code == 200


def test_labelled_entry_authorises_on_its_secret():
    client = _make_client(["laptop:s3cr3t"])
    assert client.get("/mcp", headers={"Authorization": "Bearer s3cr3t"}).status_code == 200
    assert client.get("/mcp", headers={"Authorization": "Bearer laptop"}).status_code == 401


def test_empty_tokens_disables_the_guard():
    client = _make_client([])
    r = client.get("/mcp")
    assert r.status_code == 200


def test_unprotected_path_passes_through_even_with_bad_token():
    client = _make_client(["good-token"], protect_prefix="/mcp")
    r = client.get("/v1/reminders", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 200


def test_unprotected_path_passes_through_with_no_header():
    client = _make_client(["good-token"], protect_prefix="/mcp")
    r = client.get("/v1/reminders")
    assert r.status_code == 200


async def test_non_http_scope_passes_through():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    middleware = BearerAuthMiddleware(app, ["good-token"])
    await middleware({"type": "lifespan"}, None, None)
    assert calls == ["lifespan"]
