from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from gateway.config import OwnTracksConfig

_config: OwnTracksConfig | None = None


def init(config: OwnTracksConfig) -> None:
    global _config
    _config = config


def _client() -> httpx.Client:
    assert _config and _config.base_url, "OwnTracks not configured (GATEWAY_OWNTRACKS__BASE_URL required)"
    auth = (_config.username, _config.password) if _config.username else None
    return httpx.Client(
        base_url=_config.base_url.rstrip("/"),
        auth=auth,
        timeout=15,
    )


def _fmt_point(p: dict) -> dict:
    ts = p.get("tst") or p.get("timestamp")
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
    result: dict = {
        "lat": p.get("lat"),
        "lon": p.get("lon"),
        "timestamp": dt,
        "accuracy_m": p.get("acc"),
        "altitude_m": p.get("alt"),
        "velocity_kmh": p.get("vel"),
        "user": p.get("username") or p.get("user"),
        "device": p.get("device"),
    }
    # Recorder may add a geocoded address under various keys
    for key in ("addr", "address", "locality", "friendly_name"):
        if p.get(key):
            result["address"] = p[key]
            break
    return {k: v for k, v in result.items() if v is not None}


def get_current_location(user: str = "", device: str = "") -> str:
    """Get the most recent known location. Defaults to the configured user/device.
    Returns lat, lon, timestamp, accuracy, address (if geocoded by the recorder), and velocity."""
    with _client() as c:
        params: dict = {}
        u = user or (_config.owntracks_user if _config else "")
        d = device or (_config.owntracks_device if _config else "")
        if u:
            params["user"] = u
        if d:
            params["device"] = d
        r = c.get("/api/0/last", params=params)
        r.raise_for_status()
        data = r.json()

    if not data:
        return json.dumps({"error": "No location data found"})

    # Response is a list of last-seen points (one per user/device combination)
    points = [_fmt_point(p) for p in data] if isinstance(data, list) else [_fmt_point(data)]
    if len(points) == 1:
        return json.dumps(points[0])
    return json.dumps(points)


def get_location_history(
    from_time: str = "",
    to_time: str = "",
    user: str = "",
    device: str = "",
    limit: int = 100,
) -> str:
    """Get location history. from_time and to_time are ISO 8601 strings (e.g. '2026-04-20T00:00:00Z').
    Defaults to the configured user/device. Returns a list of location points in chronological order."""
    with _client() as c:
        params: dict = {"format": "json"}
        u = user or (_config.owntracks_user if _config else "")
        d = device or (_config.owntracks_device if _config else "")
        if u:
            params["user"] = u
        if d:
            params["device"] = d
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        r = c.get("/api/0/locations", params=params)
        r.raise_for_status()
        data = r.json()

    # Recorder returns {"data": [...]} or just a list
    points_raw = data.get("data", data) if isinstance(data, dict) else data
    points = [_fmt_point(p) for p in points_raw]
    if limit:
        points = points[-limit:]
    return json.dumps({"count": len(points), "points": points})


def list_tracked_devices() -> str:
    """List all users and devices currently tracked by the OwnTracks Recorder."""
    with _client() as c:
        r = c.get("/api/0/list")
        r.raise_for_status()
        data = r.json()

    results = []
    for user_entry in data.get("results", data if isinstance(data, list) else []):
        if isinstance(user_entry, dict):
            u = user_entry.get("username") or user_entry.get("user", "")
            devices = user_entry.get("devices", [])
            results.append({"user": u, "devices": devices})
        else:
            results.append({"user": str(user_entry)})
    return json.dumps(results)


def register(mcp) -> None:
    for fn in [get_current_location, get_location_history, list_tracked_devices]:
        mcp.tool()(fn)
