from __future__ import annotations
import httpx
import pytest
import gateway.reminders.geocode as geocode
from gateway.config import RemindersConfig


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("GET", "https://x"), response=self)

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.requests: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, path, params=None):
        self.requests.append((path, params))
        return self._response


@pytest.fixture(autouse=True)
def config():
    geocode.init(RemindersConfig(nominatim_url="https://nominatim.example.com"))


def test_forward_returns_best_match(monkeypatch):
    response = FakeResponse([{"display_name": "Späti, Boxhagener Str.", "lat": "52.5200", "lon": "13.4050"}])
    fake = FakeClient(response)
    monkeypatch.setattr(geocode, "_client", lambda: fake)

    result = geocode.forward("Späti Boxhagener")

    assert result == {"name": "Späti, Boxhagener Str.", "lat": 52.52, "lon": 13.405}
    assert fake.requests == [("/search", {"q": "Späti Boxhagener", "format": "jsonv2", "limit": 1})]


def test_forward_returns_none_on_empty_results(monkeypatch):
    monkeypatch.setattr(geocode, "_client", lambda: FakeClient(FakeResponse([])))
    assert geocode.forward("nonexistent place") is None


def test_forward_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(geocode, "_client", lambda: FakeClient(FakeResponse({}, status_code=500)))
    assert geocode.forward("somewhere") is None


def test_forward_returns_none_on_network_error(monkeypatch):
    def _raise():
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(geocode, "_client", _raise)
    assert geocode.forward("somewhere") is None


def test_reverse_returns_match(monkeypatch):
    response = FakeResponse({"display_name": "Boxhagener Platz", "lat": "52.5", "lon": "13.4"})
    fake = FakeClient(response)
    monkeypatch.setattr(geocode, "_client", lambda: fake)

    result = geocode.reverse(52.5, 13.4)

    assert result == {"name": "Boxhagener Platz", "lat": 52.5, "lon": 13.4}
    assert fake.requests == [("/reverse", {"lat": 52.5, "lon": 13.4, "format": "jsonv2"})]


def test_reverse_returns_none_on_error_body(monkeypatch):
    monkeypatch.setattr(geocode, "_client", lambda: FakeClient(FakeResponse({"error": "Unable to geocode"})))
    assert geocode.reverse(0.0, 0.0) is None


def test_reverse_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(geocode, "_client", lambda: FakeClient(FakeResponse({}, status_code=500)))
    assert geocode.reverse(0.0, 0.0) is None


def test_reverse_returns_none_on_network_error(monkeypatch):
    def _raise():
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(geocode, "_client", _raise)
    assert geocode.reverse(0.0, 0.0) is None
