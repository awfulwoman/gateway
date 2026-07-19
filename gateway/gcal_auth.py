"""One-time interactive bootstrap for Google Calendar OAuth.

Run on a machine with a browser (not the headless server):

    python -m gateway.gcal_auth <credentials.json> <token.json>

Produces a token.json containing a refresh token; deploy that file and point
GATEWAY_GCAL__TOKEN_PATH at it. See docs/superpowers/specs/2026-07-19-calendar-google-migration.md.
"""
from __future__ import annotations
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python -m gateway.gcal_auth <credentials.json> <token.json>", file=sys.stderr)
        sys.exit(1)

    credentials_path, token_path = sys.argv[1], sys.argv[2]
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"Wrote {token_path}")


if __name__ == "__main__":
    main()
