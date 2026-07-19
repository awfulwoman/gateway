from __future__ import annotations
import socket
import subprocess
import sys
import time
import uuid
import httpx
import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def radicale_server(tmp_path_factory):
    """An ephemeral, filesystem-backed Radicale instance for the whole test session.
    Auth is disabled (any username/password accepted) — tests get per-test isolation
    by using a fresh random username, not by restarting the server."""
    storage = tmp_path_factory.mktemp("radicale-storage")
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "radicale",
            f"--storage-filesystem-folder={storage}",
            f"--server-hosts=127.0.0.1:{port}",
            "--auth-type=none",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base_url, timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("radicale did not start in time")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def radicale_user() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"
