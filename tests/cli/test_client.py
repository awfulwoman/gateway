from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import httpx
import pytest
from gateway.cli.client import GatewayError, call_tool


def _json_response(data):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": json.dumps(data)}],
            "isError": False,
        },
    }
    resp = MagicMock(spec=httpx.Response)
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _sse_response(data):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": json.dumps(data)}],
            "isError": False,
        },
    }
    resp = MagicMock(spec=httpx.Response)
    resp.headers = {"content-type": "text/event-stream"}
    resp.text = f"event: message\ndata: {json.dumps(payload)}\n\n"
    resp.raise_for_status = MagicMock()
    return resp


URL = "http://127.0.0.1:4000/mcp"


def test_call_tool_returns_parsed_json():
    expected = [{"title": "Meeting"}]
    with patch("httpx.post", return_value=_json_response(expected)):
        result = call_tool(URL, "list_calendar_events", {"period": "today"})
    assert result == expected


def test_call_tool_sends_correct_jsonrpc():
    with patch("httpx.post", return_value=_json_response([])) as mock_post:
        call_tool(URL, "list_calendar_events", {"period": "week"})
    body = mock_post.call_args[1]["json"]
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "list_calendar_events"
    assert body["params"]["arguments"] == {"period": "week"}


def test_call_tool_handles_sse_response():
    expected = [{"title": "Stand-up"}]
    with patch("httpx.post", return_value=_sse_response(expected)):
        result = call_tool(URL, "list_calendar_events", {"period": "today"})
    assert result == expected


def test_call_tool_raises_on_connect_error():
    with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(GatewayError, match="not running"):
            call_tool(URL, "list_calendar_events", {})


def test_call_tool_raises_on_rpc_error():
    resp = MagicMock(spec=httpx.Response)
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32601, "message": "Tool not found"},
    }
    resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=resp):
        with pytest.raises(GatewayError, match="Tool not found"):
            call_tool(URL, "nonexistent", {})


def test_call_tool_raises_on_tool_error():
    resp = MagicMock(spec=httpx.Response)
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": "Event not found: abc"}],
            "isError": True,
        },
    }
    resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=resp):
        with pytest.raises(GatewayError, match="Event not found"):
            call_tool(URL, "delete_calendar_event", {"event_id": "abc"})
