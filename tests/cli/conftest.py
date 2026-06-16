from __future__ import annotations
import os
import pytest


@pytest.fixture(autouse=True)
def clear_gateway_url(monkeypatch):
    """Ensure GATEWAY_URL env var doesn't override CLI default in tests."""
    monkeypatch.delenv("GATEWAY_URL", raising=False)
