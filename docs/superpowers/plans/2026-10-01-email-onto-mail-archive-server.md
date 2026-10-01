# §8: rewire email tools onto mail-archive-server

**Issue:** gateway#3. **Spec:** `docs/superpowers/specs/2026-09-04-mail-archive-server-handoff.md`
§8, filtered through §0's overrides (read §0 first — it wins where the two disagree).
**Now unblocked:** mail-archive-server#1 (account-scoped sync, shipped) and #2
(keyset cursor paging, shipped) both landed and are deployed and verified live.

## What changes and why

Gateway currently talks to one hardcoded IMAP account directly
(`gateway/tools/email.py`, `IMAPConfig`). Per §0's decisions:

1. **Gateway holds no IMAP credentials at all** — `IMAPConfig` is deleted, not
   deprecated (cutover, not a compat shim). Gateway's only mail config becomes
   `MailArchiveServerConfig` (base URL, bearer token, an *ergonomic* account
   allowlist — never a security control, the token already scopes that
   server-side).
2. **Every email tool goes through the archive**, including
   `fetch_unread_emails` and `mark_email_read`. For live unread state, trigger
   an account-scoped sync first (`POST /sync?account=`, mail-archive-server#1).
   `mark_email_read` calls `POST /messages/{id}/read` — which is **local-only
   for now** (mail-archive-server#3 tracks making it reach the real mailbox).
   Gateway's own tool must say so, not imply otherwise.
3. **No fallback.** With no IMAP credentials, there's nothing to fall back to:
   an unreachable archive is a clear error, never a silently empty result.
   Every archive account is both searchable and (for live/mark-read) usable —
   no `searchable`/`live` split.
4. **Paging uses the keyset cursor** (mail-archive-server#2):
   `search_emails`/`list_emails` gain `since`, `until`, `order`, `cursor`, and
   return `next_cursor` so a caller can walk a range to completion.

## Design

### Config

```python
class MailArchiveServerConfig(BaseModel):
    base_url: str = ""
    bearer_token: str = ""
    accounts: Annotated[list[str], NoDecode] = []  # ergonomic filter, empty = all in token scope

    @field_validator("accounts", mode="before")
    @classmethod
    def _split(cls, v):
        return _split_csv(v)
```

Replaces `imap: IMAPConfig` on `Config` with `mail_archive_server:
MailArchiveServerConfig`. `IMAPConfig` class deleted outright.

### Client — `gateway/mail_archive_server/store.py`

Same shape as `gateway/contacts_server/store.py`: module-level `_config`/
`_client`, `init()` building an `httpx.Client(base_url=..., headers={"Authorization":
f"Bearer {token}"}, timeout=10.0)`, `_error_message()` reading
`response.json()["error"]["message"]` (the archive's own error shape already
matches this exactly — verified against mail-archive-server's real `_error`
helper). Functions: `search(**params) -> dict`, `get_message(id) -> dict |
None` (404 -> None), `mark_read(id) -> dict`, `accounts() -> list[dict]`,
`sync(account=None) -> None`.

### Tools — `gateway/tools/email.py`, full rewrite

| Tool | Archive call | Notes |
|---|---|---|
| `search_emails` | `GET /messages` | `query`→`q`, `search_in`→`from`/`subject`/none; adds `account`, `since`, `until`, `order`, `cursor` |
| `list_emails` | `GET /messages` | becomes a thin alias: no query, just date-ordered listing with the same new params |
| `list_folders` | *(dropped)* | the archive has no folder-listing endpoint in the subset needed here — out of scope, no caller currently depends on it beyond listing; revisit if something needs it |
| `fetch_email_body` | `GET /messages/{id}` | id is the archive's own id now, not a `Message-ID` header — docstring says so plainly |
| `fetch_unread_emails` | `POST /sync?account=` per configured account, then `GET /messages?seen=false` | partial failure (one account's sync fails) must not blind the call to the others — merge what succeeded, report an `errors` list |
| `mark_email_read` | `POST /messages/{id}/read` | response passes through `upstream_synced: false` and the docstring says this plainly |
| `list_email_accounts` (new) | `GET /accounts` | reports what's actually in the archive, nothing more |

Every tool: no credentials to fall back to, so an unreachable archive
(`httpx.ConnectError`/timeout) surfaces as a clear tool error, not an empty
list.

`list_folders` being dropped is a real behaviour change — flagged, not
silently done, since the original tool list included it.

### CLI — `gateway/cli/commands/email.py`, `gateway/cli/fmt.py`

- `search`/`list`: `--account` (repeatable), `--since`, `--until`, `--order`,
  `--cursor`, drop `--folder`/`--in` (search_in) — the new backend has no
  folder-scoped search and `search_in`'s from/subject narrowing is handled by
  `--from`/`--subject` instead... *(decide narrower scope at implementation
  time if this grows the CLI surface too much for one pass; MCP tool
  correctness matters more than CLI parity for this issue)*.
- `read <id>`: now the archive's own id, not a `Message-ID`.
- `mark-read <id>`: same id; output notes `upstream_synced: false`.
- `fmt.emails()` updated for the new envelope shape (`{"messages": [...],
  "next_cursor": ..., ...}` instead of a bare list) plus an `account` column
  when a result spans more than one.

### Tests

`tests/conftest.py`: `_FakeMailArchiveServer`, mirroring `_FakeContactsServer`
exactly (session-scoped real uvicorn server, storage keyed by bearer token).
Implements the real subset of the wire contract: `GET /messages` (with
`account`, `seen`, `since`, `until`, `order`, `cursor`, `limit` and a real
keyset `next_cursor`), `GET /messages/{id}`, `POST /messages/{id}/read`,
`GET /accounts`, `POST /sync`. Seeded with at least two accounts so fan-out
paths are exercised.

`tests/test_email.py` (new, mirroring `tests/test_contacts.py`): one test per
tool, against the fake server, not mocks.

## Tasks

1. `MailArchiveServerConfig`; delete `IMAPConfig`. Config tests.
2. `gateway/mail_archive_server/store.py` + `_FakeMailArchiveServer` fixture.
   Client-level tests against the fake server.
3. `search_emails`/`list_emails`/`fetch_email_body` — the core read path
   gateway#2 (wiki-compiler's email milestone) actually needs. Tool-level
   tests.
4. `fetch_unread_emails`/`mark_email_read`/`list_email_accounts` — the
   live/write path. Tool-level tests, including the fan-out partial-failure
   case.
5. `gateway/main.py` wiring (`email.init(config.mail_archive_server)`).
6. CLI (`cli/commands/email.py`, `cli/fmt.py`). CLI tests updated.
7. Infra: `roles/composition-gateway`'s env template — replace
   `GATEWAY_IMAP__*` with `GATEWAY_MAIL_ARCHIVE_SERVER__*`, add the vaulted
   bearer token (the archive already has a `gateway`-labelled token). Cutover,
   not a compat shim — done in the same change, deployed together.
8. Deploy, verify live (real MCP call through the real gateway, against the
   real archive, same discipline as mail-archive-server's own verification).

## Out of scope for this issue

- `list_folders` (dropped — see above).
- Making `mark_email_read` reach the real mailbox (mail-archive-server#3).
- gateway#2 itself (date-range/resumable paging for *wiki-compiler*) — this
  issue unblocks it but doesn't implement it.

## Done when

- `uv run pytest` green, including new client/tool tests against the real
  fake archive server.
- `gw email search/list/read/unread/mark-read/accounts` all work against a
  running gateway pointed at the real mail-archive-server.
- Deployed; a real MCP tool call verified end-to-end against production data.
