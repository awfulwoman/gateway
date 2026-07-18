from __future__ import annotations
import httpx
from gateway.config import RemindersConfig

_config: RemindersConfig | None = None
_USER_AGENT = "gateway-reminders/1.0 (self-hosted; contact via server owner)"


def init(config: RemindersConfig) -> None:
    global _config
    _config = config


def _client() -> httpx.Client:
    assert _config and _config.nominatim_url, "Geocoding not configured (GATEWAY_REMINDERS__NOMINATIM_URL required)"
    return httpx.Client(
        base_url=_config.nominatim_url.rstrip("/"),
        headers={"User-Agent": _USER_AGENT},
        timeout=10,
    )


def forward(q: str) -> dict | None:
    """Resolve a place name to coordinates. Returns {"name", "lat", "lon"} for the
    best match, or None if there's no match or the request fails."""
    try:
        with _client() as c:
            r = c.get("/search", params={"q": q, "format": "jsonv2", "limit": 1})
            r.raise_for_status()
            results = r.json()
    except httpx.HTTPError:
        return None
    if not results:
        return None
    top = results[0]
    return {"name": top.get("display_name"), "lat": float(top["lat"]), "lon": float(top["lon"])}


def reverse(lat: float, lon: float) -> dict | None:
    """Resolve coordinates to a place name. Returns {"name", "lat", "lon"}, or None
    if there's no match or the request fails."""
    try:
        with _client() as c:
            r = c.get("/reverse", params={"lat": lat, "lon": lon, "format": "jsonv2"})
            r.raise_for_status()
            result = r.json()
    except httpx.HTTPError:
        return None
    if not result or "error" in result or "lat" not in result:
        return None
    return {"name": result.get("display_name"), "lat": float(result["lat"]), "lon": float(result["lon"])}
