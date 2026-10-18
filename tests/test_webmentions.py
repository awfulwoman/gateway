from __future__ import annotations

import json

import httpx
import pytest

import gateway.tools.webmentions as webmentions
from gateway.config import WebmentionsConfig

BASE = "https://webmention.example.com"


def item(**kw):
    base = {
        "id": "01ABC", "source": "https://other.example/r/1", "target": "https://example.com/notes/x/",
        "target_path": "/notes/x/", "status": "pending", "reason": None, "type": "reply",
        "url": "https://other.example/r/1", "author_name": "Ada", "author_url": "https://other.example/",
        "content_text": "Lovely", "received_at": "2026-10-18T09:00:00Z",
    }
    return base | kw


class Fake:
    """Records requests and answers like webmention-server's admin API."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.items = [item()]
        self.moderate_status = 200
        self.send_status = 202

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == "Bearer secret"
        path, method = request.url.path, request.method
        if path == "/admin/api/mentions" and method == "GET":
            return httpx.Response(200, json={"items": self.items, "limit": 20, "offset": 0})
        if path.startswith("/admin/api/mentions/") and method == "POST":
            if self.moderate_status != 200:
                return httpx.Response(self.moderate_status, json={"error": "a deleted mention cannot be approved"})
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[1], "status": json.loads(request.content)["status"]})
        if path == "/admin/api/send":
            if self.send_status != 202:
                return httpx.Response(self.send_status, json={"error": "sending is turned off"})
            return httpx.Response(202, json={"queued": json.loads(request.content)["source"]})
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def fake():
    f = Fake()
    webmentions.init(WebmentionsConfig(base_url=BASE, token="secret"), transport=httpx.MockTransport(f))
    return f


def test_list_defaults_to_pending_and_summarises(fake):
    out = json.loads(webmentions.list_webmentions())

    assert fake.requests[0].url.params["status"] == "pending"
    assert out == [{
        "id": "01ABC", "type": "reply", "status": "pending", "reason": None, "author": "Ada",
        "author_url": "https://other.example/", "text_from_sender": "Lovely", "on_page": "https://example.com/notes/x/",
        "from": "https://other.example/r/1", "received": "2026-10-18T09:00:00Z",
    }]


def test_list_passes_filters_through(fake):
    webmentions.list_webmentions(status="approved", type="like", page="/notes/2026", limit=5)

    params = fake.requests[0].url.params
    assert (params["status"], params["type"], params["target"], params["limit"]) == ("approved", "like", "/notes/2026", "5")


def test_long_text_is_cut(fake):
    fake.items = [item(content_text="word " * 300)]

    text = json.loads(webmentions.list_webmentions())[0]["text_from_sender"]

    assert len(text) <= 401 and text.endswith("…")


def test_missing_text_and_author_are_fine(fake):
    fake.items = [item(content_text=None, author_name=None, type=None)]

    out = json.loads(webmentions.list_webmentions())[0]

    assert (out["text_from_sender"], out["author"], out["type"]) == ("", None, None)


@pytest.mark.parametrize("kwargs", [{"status": "maybe"}, {"type": "poke"}])
def test_bad_filters_are_refused_without_a_request(fake, kwargs):
    assert "error" in json.loads(webmentions.list_webmentions(**kwargs))
    assert fake.requests == []


def test_reject(fake):
    assert json.loads(webmentions.reject_webmention("01ABC")) == {"id": "01ABC", "status": "rejected"}
    assert json.loads(fake.requests[0].content) == {"status": "rejected"}


def test_approving_is_not_possible_from_here():
    # A stranger's reply reaches the agent through list_webmentions; it must not be able to ask
    # for its own approval.
    assert not hasattr(webmentions, "moderate_webmention")
    assert not hasattr(webmentions, "approve_webmention")


def test_server_refusals_are_reported(fake):
    fake.moderate_status = 404

    out = json.loads(webmentions.reject_webmention("01NOPE"))

    assert "404" in out["error"]


def test_send(fake):
    url = "https://example.com/notes/x/"

    assert json.loads(webmentions.send_webmentions(url)) == {"queued": url}
    assert json.loads(fake.requests[0].content) == {"source": url}


def test_send_when_sending_is_off(fake):
    fake.send_status = 409

    assert "turned off" in json.loads(webmentions.send_webmentions("https://example.com/notes/x/"))["error"]


def test_unreachable_token_is_an_error_message(fake):
    webmentions.init(
        WebmentionsConfig(base_url=BASE, token="wrong"),
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "unauthorized"})),
    )

    assert "401" in json.loads(webmentions.list_webmentions())["error"]


def test_unconfigured_says_what_to_set():
    webmentions.init(WebmentionsConfig())

    with pytest.raises(AssertionError, match="GATEWAY_WEBMENTIONS__TOKEN"):
        webmentions.list_webmentions()


def test_only_the_review_and_send_tools_are_registered():
    class Recorder:
        names: list[str] = []

        def tool(self):
            def add(fn):
                self.names.append(fn.__name__)
                return fn

            return add

    rec = Recorder()
    webmentions.register(rec)

    assert rec.names == ["list_webmentions", "reject_webmention", "send_webmentions"]
