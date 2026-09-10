from __future__ import annotations
from gateway.auth import Client, client_ip, parse_clients, resolve


def test_parse_labelled_entries():
    clients = parse_clients(["laptop:abc", "gw-cli:def"])
    assert clients == [Client("laptop", "abc"), Client("gw-cli", "def")]


def test_parse_bare_token_gets_stable_fingerprint_label():
    a = parse_clients(["plain-secret"])[0]
    b = parse_clients(["plain-secret"])[0]
    assert a.secret == "plain-secret"
    assert a.label == b.label
    assert a.label.startswith("token-")


def test_parse_splits_on_first_colon_only():
    c = parse_clients(["label:sec:ret:with:colons"])[0]
    assert c == Client("label", "sec:ret:with:colons")


def test_parse_drops_blank_entries():
    assert parse_clients(["", "  ", "laptop:abc"]) == [Client("laptop", "abc")]


def test_resolve_matches_secret_returns_client():
    clients = parse_clients(["laptop:abc", "jarvis:xyz"])
    assert resolve("Bearer xyz", clients) == Client("jarvis", "xyz")


def test_resolve_no_match_returns_none():
    assert resolve("Bearer nope", parse_clients(["laptop:abc"])) is None


def test_resolve_missing_or_malformed_header_returns_none():
    clients = parse_clients(["laptop:abc"])
    assert resolve("", clients) is None
    assert resolve("Token abc", clients) is None
    assert resolve("Bearer", clients) is None


def test_resolve_empty_client_list_returns_none():
    assert resolve("Bearer abc", []) is None


def test_client_ip_prefers_forwarded_for_first_hop():
    scope = {"headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")], "client": ("172.16.0.2", 5000)}
    assert client_ip(scope) == "203.0.113.9"


def test_client_ip_falls_back_to_peer():
    assert client_ip({"headers": [], "client": ("172.16.0.2", 5000)}) == "172.16.0.2"
