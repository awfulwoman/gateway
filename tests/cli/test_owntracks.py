from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

LOCATION = {"lat": 51.5074, "lon": -0.1278, "timestamp": "2026-06-07T10:30:00+00:00", "accuracy_m": 10}
HISTORY = {"count": 2, "points": [{"lat": 51.5074, "lon": -0.1278, "timestamp": "2026-06-07T10:00:00+00:00"}, {"lat": 51.51, "lon": -0.12, "timestamp": "2026-06-07T10:30:00+00:00"}]}
DEVICES = [{"user": "charlie", "devices": ["iphone"]}]

runner = CliRunner()


def test_current():
    with patch("gateway.cli.client.call_tool", return_value=LOCATION) as mock:
        r = runner.invoke(main, ["location", "current"])
    assert r.exit_code == 0
    assert "51.5074" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_current_location", {"user": "", "device": ""})


def test_history():
    with patch("gateway.cli.client.call_tool", return_value=HISTORY) as mock:
        r = runner.invoke(main, ["location", "history"])
    assert r.exit_code == 0
    assert "Count: 2" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_location_history", {"from_time": "", "to_time": "", "user": "", "device": "", "limit": 100})


def test_devices():
    with patch("gateway.cli.client.call_tool", return_value=DEVICES) as mock:
        r = runner.invoke(main, ["location", "devices"])
    assert r.exit_code == 0
    assert "charlie" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_tracked_devices", {})
