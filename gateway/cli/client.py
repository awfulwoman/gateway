from __future__ import annotations
import json
import httpx


class GatewayError(Exception):
    pass


def call_tool(server_url: str, name: str, arguments: dict) -> list | dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    try:
        resp = httpx.post(
            server_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise GatewayError(f"gateway server is not running (tried {server_url})")
    except httpx.HTTPStatusError as e:
        raise GatewayError(f"server error: {e.response.status_code}")

    data = _parse_response(resp)

    if "error" in data:
        raise GatewayError(data["error"].get("message", "unknown error"))
    if data.get("result", {}).get("isError"):
        raise GatewayError(data["result"]["content"][0]["text"])

    return json.loads(data["result"]["content"][0]["text"])


def _parse_response(resp: httpx.Response) -> dict:
    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise GatewayError("empty SSE response from server")
    return resp.json()
