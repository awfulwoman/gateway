import json
from unittest.mock import MagicMock, patch
from gateway.config import Config, VikunjaConfig
import gateway.tools.vikunja as vikunja


def test_vikunja_config_defaults():
    c = Config()
    assert c.vikunja.base_url == ""
    assert c.vikunja.api_token == ""


def test_vikunja_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_VIKUNJA__BASE_URL", "https://vikunja.example.com")
    monkeypatch.setenv("GATEWAY_VIKUNJA__API_TOKEN", "tok-abc123")
    c = Config()
    assert c.vikunja.base_url == "https://vikunja.example.com"
    assert c.vikunja.api_token == "tok-abc123"


def _make_mock_client():
    """Returns a mock httpx client usable as context manager."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


def test_client_raises_when_not_configured():
    vikunja.init(VikunjaConfig(base_url="", api_token=""))
    import pytest
    with pytest.raises(AssertionError):
        vikunja._client()
