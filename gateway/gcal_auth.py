"""One-time interactive bootstrap for Google Calendar OAuth.

Run on a machine with a browser (not the headless server):

    python -m gateway.gcal_auth <client_id> <client_secret>

client_id/client_secret come from the OAuth "Desktop app" client in Google
Cloud Console — no need to download the credentials.json file, just copy the
two values shown on the credentials page.

Prints the resulting credentials as a single-line JSON blob on stdout. Set
that as GATEWAY_GCAL__TOKEN_JSON, e.g.:

    python -m gateway.gcal_auth <client_id> <client_secret> \\
      | ansible-vault encrypt_string --stdin-name vault_gateway_gcal_token_json

See docs/superpowers/specs/2026-07-19-calendar-google-migration.md.
"""
from __future__ import annotations
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python -m gateway.gcal_auth <client_id> <client_secret>", file=sys.stderr)
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]
    flow = InstalledAppFlow.from_client_config(_client_config(client_id, client_secret), SCOPES)
    creds = flow.run_local_server(port=0)

    print(creds.to_json())


if __name__ == "__main__":
    main()
