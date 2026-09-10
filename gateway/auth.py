from __future__ import annotations
import hashlib
import hmac
from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    """A bearer-token holder. `label` is what shows up in the usage log as the
    caller; `secret` is the token itself."""

    label: str
    secret: str


def _fingerprint(secret: str) -> str:
    return "token-" + hashlib.sha256(secret.encode()).hexdigest()[:8]


def parse_clients(raw: list[str]) -> list[Client]:
    """Turn raw `AUTH_TOKENS` entries into `Client`s. Each entry is either
    `label:secret` (split on the first colon) or a bare `secret`, which gets a
    stable `token-<fp>` label so unlabelled deployments keep working. Blank
    entries are dropped."""
    clients: list[Client] = []
    for entry in raw:
        entry = entry.strip()
        if not entry:
            continue
        label, sep, secret = entry.partition(":")
        if sep and secret:
            clients.append(Client(label=label.strip(), secret=secret.strip()))
        else:
            clients.append(Client(label=_fingerprint(entry), secret=entry))
    return clients


def resolve(auth_header: str, clients: list[Client]) -> Client | None:
    """Match an `Authorization` header value against the client list. Returns the
    matching `Client`, or `None` when the header is missing/malformed or no
    secret matches."""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    for client in clients:
        if hmac.compare_digest(token, client.secret):
            return client
    return None


def client_ip(scope) -> str:
    """Best-effort caller IP: first hop of `X-Forwarded-For` (set by Traefik),
    falling back to the ASGI peer address."""
    headers = dict(scope.get("headers") or [])
    xff = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    if xff:
        return xff.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else ""
