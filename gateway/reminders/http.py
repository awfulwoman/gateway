from __future__ import annotations
import hmac
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from gateway.config import RemindersConfig
from gateway.reminders import geocode, store

_config: RemindersConfig | None = None


def init(config: RemindersConfig) -> None:
    global _config
    _config = config


def _authorized(request: Request) -> bool:
    if not _config or not _config.api_tokens:
        return False
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = header[len("Bearer "):]
    return any(hmac.compare_digest(token, t) for t in _config.api_tokens)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


async def _json_body(request: Request) -> tuple[dict, JSONResponse | None]:
    try:
        return (await request.json()), None
    except Exception:
        return {}, _err(400, "invalid_json", "body must be valid JSON")


def _resolve_location(reminder: dict) -> tuple[dict, JSONResponse | None]:
    """If `location` names a place but has no coords, forward-geocode it. Leaves
    the reminder untouched otherwise (coords already present, or no location)."""
    loc = reminder.get("location")
    if not loc or loc.get("lat") is not None:
        return reminder, None
    name = loc.get("name")
    resolved = geocode.forward(name) if name else None
    if resolved is None:
        return reminder, _err(400, "geocode_failed", f"could not resolve location: {name!r}")
    reminder = dict(reminder)
    reminder["location"] = {**loc, "lat": resolved["lat"], "lon": resolved["lon"]}
    return reminder, None


async def get_reminders(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _err(401, "unauthorized", "missing or invalid bearer token")
    since = request.query_params.get("since") or None
    server_time = store.now_utc()
    reminders = store.list_reminders(since=since, include_deleted=True)
    return JSONResponse({"server_time": server_time, "reminders": reminders})


async def put_reminder(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _err(401, "unauthorized", "missing or invalid bearer token")
    body, error = await _json_body(request)
    if error:
        return error
    body["id"] = request.path_params["id"]

    resolved, error = _resolve_location(body)
    if error:
        return error

    try:
        stored = store.upsert(resolved)
    except store.Stale as e:
        return JSONResponse({"current": e.current}, status_code=409)
    except (ValueError, KeyError) as e:
        return _err(400, "validation_error", str(e))
    return JSONResponse(stored)


async def delete_reminder(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _err(401, "unauthorized", "missing or invalid bearer token")
    body = {}
    if await request.body():
        body, error = await _json_body(request)
        if error:
            return error

    id = request.path_params["id"]
    try:
        tombstone = store.soft_delete(id, updated_at=body.get("updated_at"))
    except KeyError:
        return _err(404, "not_found", f"no reminder with id {id!r}")
    except store.Stale as e:
        return JSONResponse({"current": e.current}, status_code=409)
    return JSONResponse(tombstone)


async def sync_reminders(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _err(401, "unauthorized", "missing or invalid bearer token")
    body, error = await _json_body(request)
    if error:
        return error

    since = body.get("since")
    changes = body.get("changes") or []

    # Captured before applying changes, per the design: nothing landed after this
    # instant is missed on the client's *next* sync, which will use it as `since`.
    server_time = store.now_utc()

    rejected = []
    for change in changes:
        resolved, change_error = _resolve_location(change)
        if change_error:
            continue
        try:
            store.upsert(resolved)
        except store.Stale as e:
            rejected.append({"id": change.get("id"), "current": e.current})
        except (ValueError, KeyError):
            continue

    reminders = store.list_reminders(since=since, include_deleted=True)
    return JSONResponse({"server_time": server_time, "reminders": reminders, "rejected": rejected})


async def get_geocode(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _err(401, "unauthorized", "missing or invalid bearer token")
    q = request.query_params.get("q")
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")

    if q:
        result = geocode.forward(q)
    elif lat is not None and lon is not None:
        try:
            result = geocode.reverse(float(lat), float(lon))
        except ValueError:
            return _err(400, "invalid_params", "lat/lon must be numbers")
    else:
        return _err(400, "invalid_params", "provide q, or both lat and lon")

    if result is None:
        return _err(404, "no_match", "no geocode match")
    return JSONResponse(result)


routes: list[Route] = [
    Route("/v1/geocode", get_geocode, methods=["GET"]),
    Route("/v1/reminders", get_reminders, methods=["GET"]),
    Route("/v1/reminders/sync", sync_reminders, methods=["POST"]),
    Route("/v1/reminders/{id}", put_reminder, methods=["PUT"]),
    Route("/v1/reminders/{id}", delete_reminder, methods=["DELETE"]),
]
