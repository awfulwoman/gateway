from __future__ import annotations

import json

import httpx
import pytest

import gateway.tools.micropub as micropub
from gateway.config import MicropubConfig

BASE = "https://indie.example.com"
POST_URL = "https://example.com/notes/2026/10/15/1200/"


class Fake:
    """Records requests and answers like micropub-server."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.create_status = 202
        self.items: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == "Bearer secret"
        path, method = request.url.path, request.method
        if path == "/media":
            return httpx.Response(201, headers={"location": "https://example.com/media/a.jpg"})
        if method == "POST":
            body = json.loads(request.content)
            if body.get("action") == "update":
                if self.create_status == 403:
                    return httpx.Response(403, json={"error": "forbidden", "error_description": "Only drafts"})
                return httpx.Response(200, headers={"location": body["url"]}, json={"success": "update"})
            return httpx.Response(self.create_status, headers={"location": POST_URL}, json={})
        q = request.url.params
        if q.get("url"):
            return httpx.Response(200, json={"type": ["h-entry"], "properties": {"uid": ["abc-123"], "name": ["Hi"]}})
        return httpx.Response(200, json={"items": self.items, "paging": {}})

    def sent(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture
def fake():
    f = Fake()
    micropub.init(MicropubConfig(base_url=BASE, token="secret"), transport=httpx.MockTransport(f))
    return f


def test_create_post_sends_mf2_json_and_returns_urls(fake):
    out = json.loads(micropub.create_post("note", {"content": "Hello", "category": ["a", "b"]}))

    assert fake.sent() == {
        "type": ["h-entry"],
        "properties": {"content": ["Hello"], "category": ["a", "b"], "mp-post-type": ["note"]},
    }
    assert out == {"url": POST_URL, "status": "draft", "edit_url": f"{BASE}/posts/abc-123/edit"}


def test_a_titled_note_says_it_is_a_note(fake):
    micropub.create_post("note", {"name": "Short Title", "content": "Hello"})

    assert fake.sent()["properties"]["mp-post-type"] == ["note"]  # else the server makes it an article


def test_page_goes_to_its_channel(fake):
    micropub.create_post("page", {"name": "Uses", "content": "My kit."})

    assert fake.sent()["properties"]["mp-channel"] == ["pages"]


def test_bandname_is_no_longer_a_type(fake):
    assert "Unknown post type" in json.loads(micropub.create_post("bandname", {"name": "x"}))["error"]


def test_checkin_becomes_an_h_card(fake):
    micropub.create_post("checkin", {"checkin": {"name": "Cafe", "latitude": 52.5, "longitude": 13.4}, "content": "Nice"})

    card = fake.sent()["properties"]["checkin"][0]
    assert card == {"type": ["h-card"], "properties": {"name": ["Cafe"], "latitude": ["52.5"], "longitude": ["13.4"]}}


def test_unknown_type_is_refused_without_a_request(fake):
    out = json.loads(micropub.create_post("poem", {"content": "x"}))

    assert "Unknown post type" in out["error"]
    assert fake.requests == []


def test_server_errors_are_reported(fake):
    fake.create_status = 403

    out = json.loads(micropub.create_post("note", {"content": "x"}))

    assert "403" in out["error"]


def test_update_post_sends_replace_add_delete(fake):
    micropub.update_post(POST_URL, replace={"name": "New"}, add={"category": "x"}, delete=["summary"])

    assert fake.sent() == {
        "action": "update", "url": POST_URL,
        "replace": {"name": ["New"]}, "add": {"category": ["x"]}, "delete": ["summary"],
    }


def test_update_of_a_published_post_surfaces_the_refusal(fake):
    fake.create_status = 403

    out = json.loads(micropub.update_post(POST_URL, replace={"name": "x"}))

    assert "Only drafts" in out["error"]


def test_get_post(fake):
    out = json.loads(micropub.get_post(POST_URL))

    assert out["properties"]["name"] == ["Hi"]
    assert fake.requests[0].url.params["url"] == POST_URL


def test_list_posts_filters_and_summarises(fake):
    fake.items = [{"type": ["h-entry"], "properties": {
        "url": [POST_URL], "post-type": ["note"], "post-status": ["draft"],
        "content": [{"value": "Hello", "html": "<p>Hello</p>"}], "published": ["2026-10-15T12:00:00+02:00"],
    }}]

    out = json.loads(micropub.list_posts(post_type="note", status="draft", limit=5))

    p = fake.requests[0].url.params
    assert (p["q"], p["post-type"], p["post-status"], p["limit"]) == ("source", "note", "draft", "5")
    assert out == [{"url": POST_URL, "type": "note", "status": "draft", "name": None,
                    "published": "2026-10-15T12:00:00+02:00", "content": "Hello"}]


def test_upload_media(fake, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    out = json.loads(micropub.upload_media(str(img)))

    assert out == {"url": "https://example.com/media/a.jpg"}
    assert b'name="file"' in fake.requests[0].content


def test_upload_media_missing_file(fake):
    assert "No such file" in json.loads(micropub.upload_media("/nope.jpg"))["error"]


def test_unconfigured_fails_clearly():
    micropub.init(MicropubConfig())
    with pytest.raises(AssertionError, match="micropub not configured"):
        micropub.list_posts()
