from __future__ import annotations
import socket
import threading
import time
import uuid
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from gateway.reminders.store import now_after, now_utc


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeRemindersServer:
    """Stands in for apple-reminders-server: implements the same wire contract
    (see apple_reminders_server/http.py) over a plain in-memory dict instead of
    EventKit. Gateway's store.py is just an HTTP client — these tests exercise
    that client against a generically-correct backend, the same role the ephemeral
    `radicale_server` above plays for the CardDAV-backed contacts store. Storage is
    keyed by bearer token so each test gets isolation via a fresh token, mirroring
    `radicale_user`, without restarting the server."""

    def __init__(self):
        self._by_token: dict[str, dict[str, dict]] = {}

    def _db(self, token: str) -> dict[str, dict]:
        return self._by_token.setdefault(token, {})

    def _authorized(self, request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        return header[len("Bearer "):]

    async def list_reminders(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        since = request.query_params.get("since")
        list_name = request.query_params.get("list")
        results = list(db.values())
        if list_name:
            results = [r for r in results if r["list"] == list_name]
        if since:
            results = [r for r in results if r["updated_at"] > since]
        results.sort(key=lambda r: r["updated_at"])
        return JSONResponse({"server_time": now_utc(), "reminders": results})

    async def get_reminder(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        if id not in db:
            return JSONResponse({"error": {"code": "not_found", "message": "no such reminder"}}, status_code=404)
        return JSONResponse(db[id])

    async def put_reminder(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        body = await request.json()
        body["id"] = request.path_params["id"]
        body["list"] = body.get("list") or "Reminders"  # server-side default, matching apple-reminders-server's own

        if not (body.get("title") or "").strip():
            return JSONResponse({"error": {"code": "validation_error", "message": "title is required and must be non-empty"}}, status_code=400)
        loc = body.get("location")
        if loc is not None and (loc.get("lat") is None or loc.get("lon") is None):
            return JSONResponse({"error": {"code": "validation_error", "message": "location requires lat and lon"}}, status_code=400)

        existing = db.get(body["id"])
        if existing is not None and body["updated_at"] <= existing["updated_at"]:
            return JSONResponse({"current": existing}, status_code=409)

        db[body["id"]] = body
        return JSONResponse(body)

    async def delete_reminder(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        existing = db.get(id)
        if existing is None:
            return JSONResponse({"error": {"code": "not_found", "message": "no such reminder"}}, status_code=404)

        body = {}
        if await request.body():
            body = await request.json()
        updated_at = body.get("updated_at") or now_after(existing["updated_at"])
        if updated_at <= existing["updated_at"]:
            return JSONResponse({"current": existing}, status_code=409)

        tombstone = dict(existing)
        tombstone["deleted"] = True
        tombstone["updated_at"] = updated_at
        db[id] = tombstone
        return JSONResponse(tombstone)

    async def gc_tombstones(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        body = await request.json() if await request.body() else {}
        cutoff_days = int(body.get("older_than_days", 30))
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_remove = [id for id, r in db.items() if r.get("deleted") and r["updated_at"] < cutoff]
        for id in to_remove:
            del db[id]
        return JSONResponse({"removed": len(to_remove)})

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/reminders", self.list_reminders, methods=["GET"]),
            Route("/reminders/{id}", self.get_reminder, methods=["GET"]),
            Route("/reminders/{id}", self.put_reminder, methods=["PUT"]),
            Route("/reminders/{id}", self.delete_reminder, methods=["DELETE"]),
            Route("/admin/gc_tombstones", self.gc_tombstones, methods=["POST"]),
        ])


class _FakeKarakeepServer:
    """Stands in for Karakeep's real API (gateway/tools/karakeep.py's only
    caller): one bookmark per id, keyed by bearer token so each test gets
    isolation without restarting the server."""

    def __init__(self):
        self._by_token: dict[str, dict[str, dict]] = {}

    def _db(self, token: str) -> dict[str, dict]:
        return self._by_token.setdefault(token, {})

    def seed(self, token: str, bookmark_id: str, bookmark: dict) -> None:
        self._db(token)[bookmark_id] = bookmark

    async def get_bookmark(self, request: Request) -> JSONResponse:
        token = request.headers.get("authorization", "")[len("Bearer "):]
        bookmark = self._db(token).get(request.path_params["id"])
        if bookmark is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(bookmark)

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/api/v1/bookmarks/{id}", self.get_bookmark, methods=["GET"]),
        ])


@pytest.fixture(scope="session")
def karakeep_server():
    """An in-process fake Karakeep for the whole test session — see
    `_FakeKarakeepServer` docstring. Per-test isolation comes from a fresh
    bearer token, not from restarting the server."""
    port = _free_port()
    fake = _FakeKarakeepServer()
    server = uvicorn.Server(uvicorn.Config(fake.app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake karakeep server did not start in time")

    yield base_url, fake

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def karakeep_server_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


class _FakeGitHubRepos:
    """The read-only slice of the GitHub REST API gateway/tools/repos.py
    calls: the owner's repo list (paginated), one repo's metadata, its
    README and CLAUDE.md as raw text, recent commits, and open issues
    (which, as on real GitHub, include pull requests). Keyed by bearer
    token so each test seeds its own repos without restarting the server.
    """

    def __init__(self):
        self._by_token: dict[str, dict[str, dict]] = {}

    def _db(self, request: Request) -> dict[str, dict]:
        token = request.headers.get("authorization", "")[len("Bearer "):]
        return self._by_token.setdefault(token, {})

    def seed(self, token: str, name: str, *, description: str = "", private: bool = False,
             fork: bool = False, archived: bool = False, pushed_at: str = "2026-10-01T00:00:00Z",
             topics: list[str] | None = None, readme: str | None = None, claude_md: str | None = None,
             commits: list[dict] | None = None, issues: list[dict] | None = None) -> None:
        self._by_token.setdefault(token, {})[name] = {
            "meta": {"name": name, "description": description, "private": private, "fork": fork,
                     "archived": archived, "pushed_at": pushed_at, "topics": topics or []},
            "readme": readme, "claude_md": claude_md,
            "commits": commits or [], "issues": issues or [],
        }

    async def list_repos(self, request: Request) -> JSONResponse:
        per_page = int(request.query_params.get("per_page", 30))
        page = int(request.query_params.get("page", 1))
        repos = [r["meta"] for r in self._db(request).values()]
        return JSONResponse(repos[(page - 1) * per_page: page * per_page])

    def _repo(self, request: Request) -> dict | None:
        return self._db(request).get(request.path_params["repo"])

    async def get_repo(self, request: Request) -> JSONResponse:
        repo = self._repo(request)
        return JSONResponse(repo["meta"]) if repo else JSONResponse({"message": "Not Found"}, status_code=404)

    async def readme(self, request: Request):
        repo = self._repo(request)
        if not repo or repo["readme"] is None:
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return PlainTextResponse(repo["readme"])

    async def contents(self, request: Request):
        repo = self._repo(request)
        if not repo or request.path_params["path"] != "CLAUDE.md" or repo["claude_md"] is None:
            return JSONResponse({"message": "Not Found"}, status_code=404)
        return PlainTextResponse(repo["claude_md"])

    async def commits(self, request: Request) -> JSONResponse:
        repo = self._repo(request)
        per_page = int(request.query_params.get("per_page", 30))
        return JSONResponse((repo["commits"] if repo else [])[:per_page])

    async def issues(self, request: Request) -> JSONResponse:
        repo = self._repo(request)
        return JSONResponse([i for i in (repo["issues"] if repo else []) if i.get("state", "open") == "open"])

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/user/repos", self.list_repos, methods=["GET"]),
            Route("/repos/{owner}/{repo}", self.get_repo, methods=["GET"]),
            Route("/repos/{owner}/{repo}/readme", self.readme, methods=["GET"]),
            Route("/repos/{owner}/{repo}/contents/{path:path}", self.contents, methods=["GET"]),
            Route("/repos/{owner}/{repo}/commits", self.commits, methods=["GET"]),
            Route("/repos/{owner}/{repo}/issues", self.issues, methods=["GET"]),
        ])


@pytest.fixture(scope="session")
def github_repos_server():
    port = _free_port()
    fake = _FakeGitHubRepos()
    server = uvicorn.Server(uvicorn.Config(fake.app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake github server did not start in time")

    yield base_url, fake

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def github_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def reminders_server():
    """An in-process fake apple-reminders-server for the whole test session — see
    `_FakeRemindersServer` docstring. Per-test isolation comes from a fresh bearer
    token (`reminders_server_token`), not from restarting the server."""
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_FakeRemindersServer().app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake reminders server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def reminders_server_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


class _FakeCalendarServer:
    """Stands in for apple-calendar-server: implements the same wire contract
    (see apple_calendar_server/http.py) over a plain in-memory dict instead of
    EventKit. Mirrors `_FakeRemindersServer` above — gateway's calendar_server/
    store.py is just an HTTP client, so these tests exercise that client against a
    generically-correct backend. Storage is keyed by bearer token for per-test
    isolation via a fresh token, without restarting the server."""

    def __init__(self):
        self._by_token: dict[str, dict[str, dict]] = {}

    def _db(self, token: str) -> dict[str, dict]:
        return self._by_token.setdefault(token, {})

    def _authorized(self, request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        return header[len("Bearer "):]

    async def list_events(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        calendar_name = request.query_params.get("calendar")
        since = request.query_params.get("since")

        results = list(db.values())
        if start:
            results = [e for e in results if e.get("deleted") or e["start"] >= start]
        if end:
            results = [e for e in results if e.get("deleted") or e["start"] <= end]
        if calendar_name:
            results = [e for e in results if e.get("calendar") == calendar_name]
        if since:
            results = [e for e in results if e["updated_at"] > since]
        results.sort(key=lambda e: e["updated_at"])
        return JSONResponse({"server_time": now_utc(), "events": results})

    async def get_event(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        if id not in db:
            return JSONResponse({"error": {"code": "not_found", "message": "no such event"}}, status_code=404)
        return JSONResponse(db[id])

    async def put_event(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        body = await request.json()
        body["id"] = request.path_params["id"]
        body["calendar"] = body.get("calendar") or "Calendar"  # server-side default, matching apple-calendar-server's own

        if not (body.get("title") or "").strip():
            return JSONResponse({"error": {"code": "validation_error", "message": "title is required and must be non-empty"}}, status_code=400)
        if not body.get("start"):
            return JSONResponse({"error": {"code": "validation_error", "message": "start is required"}}, status_code=400)
        if not body.get("end"):
            return JSONResponse({"error": {"code": "validation_error", "message": "end is required"}}, status_code=400)
        if body["end"] < body["start"]:
            return JSONResponse({"error": {"code": "validation_error", "message": "end must not be before start"}}, status_code=400)

        existing = db.get(body["id"])
        if existing is not None and body["updated_at"] <= existing["updated_at"]:
            return JSONResponse({"current": existing}, status_code=409)

        db[body["id"]] = body
        return JSONResponse(body)

    async def delete_event(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        existing = db.get(id)
        if existing is None:
            return JSONResponse({"error": {"code": "not_found", "message": "no such event"}}, status_code=404)

        body = {}
        if await request.body():
            body = await request.json()
        updated_at = body.get("updated_at") or now_after(existing["updated_at"])
        if updated_at <= existing["updated_at"]:
            return JSONResponse({"current": existing}, status_code=409)

        tombstone = dict(existing)
        tombstone["deleted"] = True
        tombstone["updated_at"] = updated_at
        db[id] = tombstone
        return JSONResponse(tombstone)

    async def get_calendars(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        names = sorted({e["calendar"] for e in db.values() if not e.get("deleted")})
        return JSONResponse({"calendars": names})

    async def gc_tombstones(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        body = await request.json() if await request.body() else {}
        cutoff_days = int(body.get("older_than_days", 30))
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_remove = [id for id, e in db.items() if e.get("deleted") and e["updated_at"] < cutoff]
        for id in to_remove:
            del db[id]
        return JSONResponse({"removed": len(to_remove)})

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/events", self.list_events, methods=["GET"]),
            Route("/events/{id}", self.get_event, methods=["GET"]),
            Route("/events/{id}", self.put_event, methods=["PUT"]),
            Route("/events/{id}", self.delete_event, methods=["DELETE"]),
            Route("/calendars", self.get_calendars, methods=["GET"]),
            Route("/admin/gc_tombstones", self.gc_tombstones, methods=["POST"]),
        ])


@pytest.fixture(scope="session")
def calendar_server():
    """An in-process fake apple-calendar-server for the whole test session — see
    `_FakeCalendarServer` docstring. Per-test isolation comes from a fresh bearer
    token (`calendar_server_token`), not from restarting the server."""
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_FakeCalendarServer().app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake calendar server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def calendar_server_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


class _FakeContactsServer:
    """Stands in for apple-contacts-server: implements the same wire contract (see
    apple_contacts_server/http.py) over a plain in-memory dict instead of the
    Contacts framework. Mirrors `_FakeRemindersServer`/`_FakeCalendarServer` above —
    gateway's contacts_server/store.py is just an HTTP client. Unlike those two,
    there's no LWW/tombstone contract to fake here (see apple-contacts-server's own
    store.py docstring): writes are plain last-write-wins and deletes are real.
    Storage is keyed by bearer token for per-test isolation via a fresh token,
    without restarting the server."""

    def __init__(self):
        self._by_token: dict[str, dict[str, dict]] = {}

    def _db(self, token: str) -> dict[str, dict]:
        return self._by_token.setdefault(token, {})

    def _authorized(self, request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        return header[len("Bearer "):]

    async def list_contacts(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        results = sorted(db.values(), key=lambda c: c["name"].lower())
        return JSONResponse({"contacts": results})

    async def get_contact(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        if id not in db:
            return JSONResponse({"error": {"code": "not_found", "message": "no such contact"}}, status_code=404)
        return JSONResponse(db[id])

    async def put_contact(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        body = await request.json()
        body["id"] = request.path_params["id"]

        if not (body.get("name") or "").strip():
            return JSONResponse({"error": {"code": "validation_error", "message": "name is required and must be non-empty"}}, status_code=400)

        db[body["id"]] = body
        return JSONResponse(body)

    async def delete_contact(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        db = self._db(token)
        id = request.path_params["id"]
        if id not in db:
            return JSONResponse({"error": {"code": "not_found", "message": "no such contact"}}, status_code=404)
        del db[id]
        return JSONResponse({"status": "deleted", "id": id})

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/contacts", self.list_contacts, methods=["GET"]),
            Route("/contacts/{id}", self.get_contact, methods=["GET"]),
            Route("/contacts/{id}", self.put_contact, methods=["PUT"]),
            Route("/contacts/{id}", self.delete_contact, methods=["DELETE"]),
        ])


@pytest.fixture(scope="session")
def contacts_server():
    """An in-process fake apple-contacts-server for the whole test session — see
    `_FakeContactsServer` docstring. Per-test isolation comes from a fresh bearer
    token (`contacts_server_token`), not from restarting the server."""
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_FakeContactsServer().app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake contacts server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def contacts_server_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


class _FakeMailArchiveServer:
    """Stands in for mail-archive-server's real wire contract (verified
    against its own http.py/store.py, not guessed): GET /messages (account,
    seen, since, until, order, cursor, limit), GET /messages/{id}, POST
    /messages/{id}/read, GET /accounts, POST /sync. Storage keyed by bearer
    token for per-test isolation, mirroring `_FakeContactsServer`.

    Messages are seeded directly (`seed()`), not synced from a real Maildir
    -- gateway's own tools treat the archive as an opaque HTTP API, so this
    only needs to be wire-compatible, not byte-for-byte reimplement the real
    server's SQL. The cursor is a simple index-into-the-sorted-list token,
    opaque to any caller exactly like the real one.
    """

    def __init__(self):
        self._by_token: dict[str, list[dict]] = {}
        self.sync_calls: list[str | None] = []

    def _db(self, token: str) -> list[dict]:
        return self._by_token.setdefault(token, [])

    def seed(self, token: str, messages: list[dict]) -> None:
        # Copy each dict -- post_mark_read mutates its stored message
        # in place (`m["seen"] = True`), and callers often seed from a
        # shared module-level constant; without a copy, one test's
        # mark-read would silently corrupt every other test's fixture data.
        self._db(token).extend(dict(m) for m in messages)

    def _authorized(self, request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        return header[len("Bearer "):]

    async def get_messages(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)

        qp = request.query_params
        rows = list(self._db(token))
        accounts = qp.getlist("account")
        if accounts:
            rows = [m for m in rows if m["account"] in accounts]
        seen = qp.get("seen")
        if seen is not None:
            rows = [m for m in rows if m["seen"] == (seen == "true")]
        since = qp.get("since")
        if since:
            rows = [m for m in rows if m["date"] >= since]
        until = qp.get("until")
        if until:
            rows = [m for m in rows if m["date"] <= until]

        order = qp.get("order", "date_desc")
        rows.sort(key=lambda m: (m["date"], m["id"]), reverse=(order == "date_desc"))

        cursor = qp.get("cursor")
        start = int(cursor) if cursor else 0
        limit = int(qp.get("limit", "25"))
        page = rows[start:start + limit]
        next_cursor = str(start + limit) if start + limit < len(rows) else None

        return JSONResponse({
            "messages": page, "total": len(rows), "limit": limit, "offset": 0,
            "next_cursor": next_cursor, "accounts_searched": accounts or sorted({m["account"] for m in rows}),
            "index": {"last_indexed_at": "2026-01-01T00:00:00Z", "oldest_sync_at": "2026-01-01T00:00:00Z",
                      "stale_seconds": 60},
        })

    async def get_message_detail(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        id_ = request.path_params["id"]
        for m in self._db(token):
            if m["id"] == id_:
                return JSONResponse(m)
        return JSONResponse({"error": {"code": "not_found", "message": "no such message"}}, status_code=404)

    async def post_mark_read(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        id_ = request.path_params["id"]
        for m in self._db(token):
            if m["id"] == id_:
                m["seen"] = True
                return JSONResponse({"id": id_, "account": m["account"], "seen": True, "upstream_synced": False})
        return JSONResponse({"error": {"code": "not_found", "message": "no such message"}}, status_code=404)

    async def get_accounts(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        names = sorted({m["account"] for m in self._db(token)})
        return JSONResponse({"accounts": [
            {"name": n, "messages": sum(1 for m in self._db(token) if m["account"] == n),
             "last_sync_attempt_at": "2026-01-01T00:00:00Z", "last_sync_ok": True}
            for n in names
        ]})

    async def post_sync(self, request: Request) -> JSONResponse:
        token = self._authorized(request)
        if not token:
            return JSONResponse({"error": {"code": "unauthorized", "message": "missing bearer token"}}, status_code=401)
        account = request.query_params.get("account")
        if account is not None and account not in {m["account"] for m in self._db(token)}:
            return JSONResponse({"error": {"code": "unknown_account", "message": f"unknown account: {account}"}},
                                 status_code=400)
        self.sync_calls.append(account)
        return JSONResponse({"indexing": True}, status_code=202)

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/messages", self.get_messages, methods=["GET"]),
            Route("/messages/{id}", self.get_message_detail, methods=["GET"]),
            Route("/messages/{id}/read", self.post_mark_read, methods=["POST"]),
            Route("/accounts", self.get_accounts, methods=["GET"]),
            Route("/sync", self.post_sync, methods=["POST"]),
        ])


@pytest.fixture(scope="session")
def mail_archive_server():
    """An in-process fake mail-archive-server for the whole test session --
    see `_FakeMailArchiveServer` docstring. Per-test isolation comes from a
    fresh bearer token, not from restarting the server."""
    port = _free_port()
    fake = _FakeMailArchiveServer()
    server = uvicorn.Server(uvicorn.Config(fake.app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("fake mail archive server did not start in time")

    yield base_url, fake

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def mail_archive_server_token() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"
