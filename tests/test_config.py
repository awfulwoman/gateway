from __future__ import annotations
from gateway.config import Config


def test_reminders_api_tokens_split_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_REMINDERS__API_TOKENS", "device-a, device-b,device-c")
    monkeypatch.setenv("GATEWAY_REMINDERS__DB_PATH", "/tmp/reminders-test.db")
    config = Config()
    assert config.reminders.api_tokens == ["device-a", "device-b", "device-c"]
    assert config.reminders.db_path == "/tmp/reminders-test.db"


def test_reminders_api_tokens_defaults_empty():
    config = Config()
    assert config.reminders.api_tokens == []
