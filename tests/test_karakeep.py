"""Found live: a real production run crashed inside get_bookmark_content
with `TypeError: expected string or bytes-like object, got 'NoneType'`.
Karakeep returns `"htmlContent": null` for a link bookmark it hasn't
crawled (yet, or at all) -- `.get("htmlContent", "")` only substitutes the
default when the key is *missing*, not when it's present and null, so
`text` ends up `None` and the HTML-stripping regex blows up on it.
"""

from __future__ import annotations

import json

import pytest

import gateway.tools.karakeep as karakeep
from gateway.config import KarakeepConfig


@pytest.fixture
def kk(karakeep_server, karakeep_server_token):
    base_url, fake = karakeep_server
    karakeep.init(KarakeepConfig(base_url=base_url, api_key=karakeep_server_token))
    fake.seed(karakeep_server_token, "has-content", {
        "id": "has-content", "content": {"type": "link", "htmlContent": "<p>Hello <b>world</b></p>"},
    })
    fake.seed(karakeep_server_token, "uncrawled", {
        "id": "uncrawled", "content": {"type": "link", "htmlContent": None},
    })
    fake.seed(karakeep_server_token, "text-null", {
        "id": "text-null", "content": {"type": "text", "text": None},
    })
    return karakeep


def test_get_bookmark_content_strips_html(kk):
    result = json.loads(kk.get_bookmark_content("has-content"))
    assert result["content"] == "Hello world"


def test_get_bookmark_content_handles_an_uncrawled_link_bookmark(kk):
    result = json.loads(kk.get_bookmark_content("uncrawled"))
    assert result["content"] == ""


def test_get_bookmark_content_handles_a_null_text_field(kk):
    result = json.loads(kk.get_bookmark_content("text-null"))
    assert result["content"] == ""
