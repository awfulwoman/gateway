from __future__ import annotations
import os
import pytest
from gateway.cli import client


@pytest.fixture(autouse=True)
def clear_gateway_url(monkeypatch):
    """Ensure GATEWAY_URL env var doesn't override CLI default in tests."""
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    monkeypatch.delenv("GATEWAY_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def reset_client_token(monkeypatch):
    """Isolate gateway.cli.client's module-level token across tests."""
    monkeypatch.setattr(client, "_token", "")
