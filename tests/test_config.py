from __future__ import annotations
from gateway.config import Config


def test_reminders_api_tokens_split_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS__API_TOKENS", "device-a, device-b,device-c")
    config = Config()
    assert config.reminders.api_tokens == ["device-a", "device-b", "device-c"]


def test_reminders_api_tokens_defaults_empty():
    config = Config()
    assert config.reminders.api_tokens == []


def test_radicale_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_RADICALE__BASE_URL", "https://radicale.internal")
    monkeypatch.setenv("GATEWAY_RADICALE__USERNAME", "gateway")
    monkeypatch.setenv("GATEWAY_RADICALE__PASSWORD", "secret")
    monkeypatch.setenv("GATEWAY_RADICALE__CONTACTS_PATH", "/gateway/contacts/")
    config = Config()
    assert config.radicale.base_url == "https://radicale.internal"
    assert config.radicale.username == "gateway"
    assert config.radicale.password == "secret"
    assert config.radicale.contacts_path == "/gateway/contacts/"


def test_reminders_server_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS_SERVER__BASE_URL", "https://apple-reminders.internal")
    monkeypatch.setenv("GATEWAY_REMINDERS_SERVER__BEARER_TOKEN", "secret")
    config = Config()
    assert config.reminders_server.base_url == "https://apple-reminders.internal"
    assert config.reminders_server.bearer_token == "secret"


def test_calendar_server_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_CALENDAR_SERVER__BASE_URL", "https://apple-calendar.internal")
    monkeypatch.setenv("GATEWAY_CALENDAR_SERVER__BEARER_TOKEN", "secret")
    config = Config()
    assert config.calendar_server.base_url == "https://apple-calendar.internal"
    assert config.calendar_server.bearer_token == "secret"
