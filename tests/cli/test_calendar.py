from __future__ import annotations
import json
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

EVENTS = [{"event_id": "abc", "title": "Stand-up", "start": "2026-06-07 09:00:00 +0000", "end": "2026-06-07 09:30:00 +0000", "all_day": False, "location": "", "notes": "", "calendar": "Work", "url": ""}]
CALENDARS = [{"name": "Work", "id": "c1", "color": "blue"}]

runner = CliRunner()


def test_list_events_human():
    with patch("gateway.cli.client.call_tool", return_value=EVENTS):
        r = runner.invoke(main, ["calendar", "list-events", "today"])
    assert r.exit_code == 0, r.output
    assert "Stand-up" in r.output


def test_list_events_json():
    with patch("gateway.cli.client.call_tool", return_value=EVENTS):
        r = runner.invoke(main, ["calendar", "list-events", "today", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)[0]["title"] == "Stand-up"


def test_list_events_passes_args():
    with patch("gateway.cli.client.call_tool", return_value=[]) as mock:
        runner.invoke(main, ["calendar", "list-events", "week"])
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_calendar_events", {"period": "week"})


def test_list_calendars():
    with patch("gateway.cli.client.call_tool", return_value=CALENDARS):
        r = runner.invoke(main, ["calendar", "list-calendars"])
    assert r.exit_code == 0
    assert "Work" in r.output


def test_search_events():
    with patch("gateway.cli.client.call_tool", return_value=EVENTS) as mock:
        r = runner.invoke(main, ["calendar", "search", "stand"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_calendar_events", {"query": "stand", "days_ahead": 90})


def test_create_event():
    result = {"status": "created", "title": "Meeting", "start": "2026-06-08T14:00:00", "end": "2026-06-08T15:00:00"}
    with patch("gateway.cli.client.call_tool", return_value=result) as mock:
        r = runner.invoke(main, ["calendar", "create", "Meeting", "2026-06-08T14:00:00", "2026-06-08T15:00:00"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_calendar_event", {
        "title": "Meeting", "start_iso": "2026-06-08T14:00:00", "end_iso": "2026-06-08T15:00:00",
        "location": "", "notes": "", "calendar_name": "",
    })


def test_delete_event():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "event_id": "abc"}) as mock:
        r = runner.invoke(main, ["calendar", "delete", "abc"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_calendar_event", {"event_id": "abc"})


def test_gateway_error_shown():
    from gateway.cli.client import GatewayError
    with patch("gateway.cli.client.call_tool", side_effect=GatewayError("not running")):
        r = runner.invoke(main, ["calendar", "list-events", "today"])
    assert r.exit_code != 0
    assert "not running" in r.output
