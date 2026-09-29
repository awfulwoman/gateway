# mail-archive-server — build handoff

**Date:** 2026-09-04
**Status:** Partly implemented, and superseded in places. Read §0 first.
**Audience:** the agent/developer implementing this. This document is
**self-contained**: it names every file to touch across three repositories, the
exact wire contract, and the acceptance checks. You should not need to rediscover
any of the findings in §2.

---

## 0. Status as of 2026-09-29

Most of this document is built, but not always as written. Where this section
and the rest of the document disagree, this section wins.

| Section | Status |
|---|---|
| §4 mbsync fix | **Superseded.** `system-emailbackup` was retired on 2026-09-18 (infra `734069d6`). Sync moved into the service. |
| §5 Multi-account backup | **Superseded.** Accounts are in `charlie_email_accounts` in infra (`personal`, `gmail_seuk`, `gmail_taw`, `gmail_se`, `shared`). The service syncs them itself; there is no backup role and no migration. |
| §6 The service | **Built** in `awfulwoman/mail-archive-server`. It also owns IMAP sync: it runs mbsync per account on a timer (`MAIL_ARCHIVE_SYNC_INTERVAL_SECONDS`, hourly) and exposes `POST /sync`. |
| §7 Infra | **Built and deployed** as a Docker composition, `composition-mail-archive-server`, not a systemd role. Data is at `fastpool/compositions/mail-archive-server` (ZFS policy `critical`). The old Maildir remains at `/slowpool/charlie/email` as a historical copy. |
| §8 Gateway | **Not started.** Gateway still uses single-account direct IMAP. |

### Decisions that change §8

1. **Gateway holds no IMAP credentials.** The service is the only holder of mail
   credentials. §8.1's `IMAPAccountConfig` / `imap_accounts` /
   `imap_default_account`, and the matching `GATEWAY_IMAP_ACCOUNTS__*` template in
   §7.4, are **dropped**. Gateway's only mail config is `MailArchiveServerConfig`.
2. **Every email tool uses the archive**, including `fetch_unread_emails` and
   `mark_email_read`. For current unread state, Gateway triggers an
   account-scoped sync first. To mark a message read, the service sets the flag
   in its own Maildir and syncs it back upstream. Both need new service endpoints:
   `awfulwoman/mail-archive-server#1`.
3. **No IMAP fallback.** With no credentials, Gateway has nothing to fall back to.
   If the archive is unreachable, the tools return a clear error, never an empty
   result. §8.3 "Graceful degradation", the `"source": "archive" | "imap"` field,
   and acceptance item 20 are dropped.
4. **Live and searchable are the same set.** Every archive account is both
   searchable and markable, so the `searchable` / `live` split in §8.3 and
   acceptance item 17 no longer applies. `list_email_accounts` reports the
   archive's accounts and their sync health.
5. **Paging uses a keyset cursor**, not `offset`: `awfulwoman/mail-archive-server#2`
   and `awfulwoman/gateway#2`.

---

## 1. What you are building

A small authorised REST API — `mail-archive-server` — that serves **indexed search
over the mbsync Maildir backup** of Charlie's mailboxes, plus the Gateway client
that consumes it, plus **multi-account support** in the backup itself.

The goal is to make email search fast and expressive (full-text, date ranges,
sender, **attachment filtering**, **across multiple accounts**) without Gateway
owning any mail state.

### In scope

- Multi-account rewrite of the `system-emailbackup` role, with a **no-redownload
  migration** of the existing 1.5 GB single-account archive (§5).
- New repo `awfulwoman/mail-archive-server`: Maildir indexer + read-only HTTP API,
  account-aware throughout (§6).
- New Ansible role `system-mail-archive-server` on `server-64gb-storage` (§7).
- Gateway client + rewired email tools and `gw email` CLI (§8).
- **Account discovery, not account duplication**: the archive serves **every account
  its token is scoped to** by default, and Gateway *discovers* them via
  `GET /accounts` rather than re-listing them in its own config. An optional
  Gateway-side allowlist narrows that for ergonomics (§8.1).
- **Token-scoped access** on the archive: bearer tokens carry an account scope,
  enforced server-side, because that — not the client's allowlist — is the security
  boundary (§6.5).
- **Multi-account live IMAP**: `GATEWAY_IMAP__*` becomes a map of named accounts, so
  unread state and writes work per account too. Unlike the archive path this cannot
  be discovered — it needs credentials (§8.1, §8.3).
- Fixing the mbsync backup, which has **failed every run on record** and reported
  this to nobody, and adding the alerting that would have caught it (§4) — do this
  **first**.

### Out of scope

- Writing to the Maildir. The service is **strictly read-only** on mail data.
- Replacing IMAP entirely. Unread state and all writes stay on IMAP (§8.3).
- Attachment *payload* serving. Index attachment metadata only (filename, type,
  size). Bodies yes, attachment bytes no.
- Any autonomous LLM behaviour. Gateway's `CLAUDE.md` forbids it; this service
  contains no LLM calls at all.

---

## 2. What already exists (verified on the live host, 2026-09-04)

Trust these findings; re-verify only if something contradicts them.

### 2.1 The backup

`awfulwoman/infra` role `system-emailbackup` runs **mbsync (isync 1.4.4)** pulling
one mailbox to Maildir:

| Property | Value |
|---|---|
| Path | `/slowpool/charlie/email` (ZFS dataset, provisioned by `system-zfs`) |
| Host | `server-64gb-storage` (`playbooks/hosts/server-64gb-storage/core.yaml:46`) |
| Config template | `roles/system-emailbackup/templates/mbsyncrc.j2` |
| Channel | a single one, named `main` |
| Patterns | `*` (all folders) |
| Expunge | `None` — deleted mail is **flagged `T`, not removed** (§6.6, §6.7) |
| SubFolders | `Verbatim` — nested folders are real nested directories |
| Sync state | `/slowpool/charlie/email/.mbsync/` |
| Schedule | `daily`, `RandomizedDelaySec=300`, `Persistent=true` |
| Owner | `ansible_user` (`awful`) |

Live contents — 1.5 GB, ~24.4k messages:

```
INBOX   cur=19232 new=387      Archive cur=3930 new=1046
Trash   cur=2024  new=662      Sent    cur=956  new=0
Junk    cur=130   new=33       Drafts  cur=1    new=0
Amazon  cur=0     new=0        Later   cur=0    new=0
```

Real nesting exists: `Archive/{2019,2020,2021,2022}`, `INBOX/Amazon`,
`Trash/{test,Hello,Herself,Ooooh,INBOXnullTimidra.in}`.

### 2.2 Sync-state file naming — the fact that makes migration safe

`/slowpool/charlie/email/.mbsync/` holds 18 files named by **box**, with `!` as the
hierarchy separator, and **no channel prefix**:

```
INBOX  Archive  Archive!2019  Archive!2020  Archive!2021  Archive!2022
Sent  Junk  Drafts  Trash  Trash!Hello  Trash!Ooooh  …  Amazon  INBOX!Amazon
```

Each contains the UID bookkeeping, e.g.:

```
FarUidValidity 1559118755
NearUidValidity 1775253733
MaxPulledUid 0
MaxPushedUid 0
```

**Consequence 1:** renaming the channel from `main` to an account name does *not*
invalidate state, because state filenames derive from box names, not the channel.
The §5 migration is therefore a pure `mv` with **no re-download**.

**Consequence 2:** two channels sharing one `SyncState` directory would collide on
these filenames. Each account **must** get its own `SyncState` directory.

### 2.3 Co-location — the reason this design works

`composition-gateway` **also** runs on `server-64gb-storage` (via
`system-compositions`; see `inventory/host_vars/server-64gb-storage/core.yaml:171`).
The Gateway container and the full Maildir are already on the same machine, and
the mail is already on that disk in plaintext inside the ZFS backup set. This
service adds **no new data custody** — it reads what is already there.

### 2.4 The pattern to copy

Three services already follow the shape this one must follow:

| Service | Port | Gateway client |
|---|---|---|
| `apple-reminders-server` | 4100 | `gateway/reminders/store.py` |
| `apple-calendar-server` | 4101 | `gateway/calendar_server/store.py` |
| `apple-contacts-server` | 4102 | `gateway/contacts_server/store.py` |
| **`mail-archive-server`** | **4103** | **`gateway/mail_archive_server/store.py`** |

Each is a bearer-token REST API; Gateway holds only a thin `httpx` client. Note
that `apple-reminders-server` already owns a **sidecar SQLite** database
(`system_apple_reminders_server_db_path`) — precedent for this service owning its
index while Gateway stays stateless.

Unlike the three above, this service runs on **Linux**, so none of the macOS
complexity applies: no TCC, no code signing, no LaunchAgent. A plain systemd unit.

### 2.5 Current email implementation (what you are replacing)

`gateway/tools/email.py` — direct `imaplib` against `imap.mailbox.org`:

- `search_emails` (`:116-142`) filters only by `search_in` ∈ {subject, from, body,
  all}, mapped to raw IMAP `SEARCH`. **No attachment filter exists**, and RFC 3501
  `SEARCH` has no portable way to express one.
- It fetches **full bodies** (`BODY.PEEK[]`, `:137`) for every hit purely to cut a
  400-char preview (`:140`). This is the main performance defect.
- Every call opens a fresh IMAP4_SSL connection and logs in (`:19-21`).
- Headers are not RFC 2047-decoded, so non-ASCII subjects come out mangled.
- `IMAPConfig` (`gateway/config.py`) is a **single** account — one host, username
  and password. §8.1 replaces it with a map of named accounts.

---

## 3. Architecture

```
mailbox.org ─┐
  work IMAP ─┼── mbsync (hourly, one unit per account)
   other    ─┘        │
                      ▼
        /slowpool/charlie/email/<account>/<folder>/{cur,new,tmp}
                      │ read-only
                      ▼
          mail-archive-server  :4103
          (SQLite FTS5 index, owns it)
                      │ HTTP + bearer
                      ▼
             Gateway container  :4000
             (stateless proxy, owns nothing)
                      │
                MCP tools / gw CLI
```

**The invariant you must not break:** Gateway owns no mail state, no index, no
filesystem mount. It holds a `base_url` and a token. All derived state lives in
the service.

---

## 4. Work item 0 — fix mbsync first

### 4.1 The unit has never succeeded

Not "is currently failing" — the journal holds **27 failures and zero successes**,
every run from its earliest entry (2026-08-10) through 2026-09-04. The journal does
not reach further back, so the true duration is unknown and probably longer.

```
Error: channel main: far side box INBOX/Amazon cannot be opened.
emailbackup.service: Main process exited, code=exited, status=1/FAILURE
```

**Nothing reported this.** The unit has no `OnFailure=`, and there is no systemd
failure-notification pattern anywhere in the infra repo — `monitoring-healthchecksio`
wraps Ansible *playbook* runs, not this unit. A daily backup silently failing for a
month is the actual defect here; the stale mailbox is only its trigger.

**Mail is not being lost.** The last run opened 18 boxes and raised exactly 1 error;
INBOX and Trash hold messages timestamped 2026-09-04. Per `man mbsync`, an
unopenable far-side box makes mbsync "skip that mailbox pair" — the other 17 sync
normally and it exits 1 afterwards. So the data is sound and the *exit code* is the
lie. That is precisely why it went unnoticed.

### 4.2 It is structurally guaranteed to recur

From `man mbsync`:

> `Remove {None|Far|Near|Both}` — Propagate mailbox deletions […]. **Otherwise print
> an error message and skip that mailbox pair if a mailbox does not exist but the
> corresponding sync state does.** (Global default: None)

`mbsyncrc.j2` sets no `Remove`, so it is `None`. Combined with `Create Near` (which
creates local folders) and nothing that ever removes them, **every folder deleted
server-side becomes a permanent daily error**. Three already have: `INBOX/Amazon`,
`Amazon` and `Later`. Deleting one more mail folder in webmail re-breaks the unit.

Cleaning up the three stale directories is therefore a treadmill, not a fix.

### 4.3 What to do

**Do not index a backup that reports `failed`.** All three parts, in order:

1. **Alerting first** — it is what makes everything else verifiable. Add
   `OnFailure=` to the backup unit(s) pointing at a notification service, and prove
   it fires by deliberately failing a run. Without this, a future regression is
   again invisible for a month. This is the highest-value change in this document
   and is worth shipping on its own.

2. **Clean up the three stale folders.** All verified empty — each contains only a
   `.uidvalidity` marker, and their state files record `MaxPulledUid 0`. Re-confirm
   before deleting (`find … -type f`), then remove the directories
   `INBOX/Amazon`, `Amazon`, `Later` and their state files `.mbsync/INBOX!Amazon`,
   `.mbsync/Amazon`, `.mbsync/Later`. Run the unit and confirm exit 0 — the **first
   success on record**.

3. **Set `Remove Near`** in `mbsyncrc.j2` so vanished remote folders stop
   accumulating. Two things to know before adopting it:
   - The man page warns "for safety, non-empty mailboxes are never deleted", which
     is the behaviour you want — an archive folder with mail in it is protected.
   - **What is not documented is whether a *non-empty* vanished box still errors.**
     Test this deliberately (create a remote folder, sync, put mail in the local
     copy, delete the remote folder, sync) and record the answer in the role's
     README. If it does still error, that is arguably correct — a folder with mail
     disappearing server-side is something you want to be told about — but you must
     know which it is before trusting the exit code.
   - Note the Maildir nuance: deleting the `cur/` subdirectory is sufficient to mark
     a mailbox deleted, which keeps `SyncState *` compatibility.

Consider whether `Remove Near` fits the archive's intent at all: `Expunge None` says
"keep mail the server no longer has". `Remove Near` is the folder-level opposite.
The non-empty safety net reconciles them for the observed case (empty husks), but if
you would rather keep every folder forever, keep `Remove None` and instead treat
"cannot be opened" as an expected condition in the alerting layer — never by
blanket-ignoring mbsync's exit code, which would re-hide real failures.

§5.4 additionally makes any recurrence *non-fatal to other accounts* by giving each
account its own systemd unit.

---

## 5. Multi-account backup — `roles/system-emailbackup`

### 5.1 Target layout

```
/slowpool/charlie/email/
  personal/                 # account name
    INBOX/{cur,new,tmp}
    Archive/2019/{cur,…}
    …
  work/
    INBOX/{cur,new,tmp}
  .mbsync/
    personal/               # per-account state dir — REQUIRED, see §2.2
      INBOX  Archive  Archive!2019  …
    work/
```

### 5.2 Configuration

Replace the scalar IMAP vars in `roles/system-emailbackup/defaults/main.yaml` with
a list, keeping a backwards-compatible default derived from the existing vars so an
un-migrated host still works:

```yaml
emailbackup_accounts:
  - name: personal
    imap_host: "imap.{{ vault_mailprovider_domain }}"
    imap_user: "{{ vault_mailprovider_user }}"
    imap_password: "{{ vault_mailprovider_password }}"
```

`name` must match `^[a-z0-9][a-z0-9_-]*$` — it is used as a directory name **and** a
systemd instance name, and it is the `account` value the REST API reports. Assert
this in the role; a name needing systemd escaping will cause confusing failures.

### 5.3 `mbsyncrc.j2`

One config file, one `IMAPAccount`/`IMAPStore`/`MaildirStore`/`Channel` block per
account, looping over `emailbackup_accounts`. Channel name = account name.

```jinja
{% for acct in emailbackup_accounts %}
IMAPAccount {{ acct.name }}
Host {{ acct.imap_host }}
User {{ acct.imap_user }}
Pass {{ acct.imap_password }}
SSLType IMAPS
CertificateFile /etc/ssl/certs/ca-certificates.crt

IMAPStore {{ acct.name }}-remote
Account {{ acct.name }}

MaildirStore {{ acct.name }}-local
Path {{ emailbackup_storage_path }}/{{ acct.name }}/
Inbox {{ emailbackup_storage_path }}/{{ acct.name }}/INBOX
SubFolders Verbatim

Channel {{ acct.name }}
Far :{{ acct.name }}-remote:
Near :{{ acct.name }}-local:
Patterns {{ acct.patterns | default('*') }}
Create Near
Expunge None
SyncState {{ emailbackup_storage_path }}/.mbsync/{{ acct.name }}/

{% endfor %}
```

Keep mode `0600` — it holds every account's password.

`patterns` is per-account and defaults to `*`, so a provider needing exclusions
(e.g. Gmail's `[Gmail]/All Mail` duplicating everything) can be handled without a
role change.

### 5.4 Per-account systemd units

Replace `emailbackup.service`/`.timer` with **template units** so one account's
failure cannot fail the others — directly addressing §4's failure mode:

- `emailbackup@.service` — `Type=oneshot`,
  `ExecStart=/usr/bin/mbsync -c /home/%u/.mbsyncrc -V %i` (`%i` = channel = account),
  plus `OnFailure=` per §4.3 so a failing account actually reports. The instance name
  must appear in the notification — "the email backup failed" is not actionable when
  there are several.
- `emailbackup@.timer` — `OnCalendar={{ emailbackup_sync_schedule }}`,
  `RandomizedDelaySec=300`, `Persistent=true`.
- Enable `emailbackup@<name>.timer` for each account; **disable and remove the old
  non-templated units** so they cannot run alongside.

Set the schedule to hourly (mbsync is incremental, so this is cheap and cuts
staleness 24×). In `inventory/host_vars/server-64gb-storage/core.yaml`:

```yaml
emailbackup_sync_schedule: hourly
```

### 5.5 Migration — must not trigger a re-download

1.5 GB is at stake. Because state files are box-named (§2.2), moving them into a
per-account subdirectory preserves sync state exactly.

Run once on `server-64gb-storage`, before the new role:

1. `systemctl stop emailbackup.timer emailbackup.service`.
2. Record a baseline: total message-file count and `du -sh`.
3. `mkdir /slowpool/charlie/email/personal`.
4. Move the eight mail folders (`INBOX Archive Sent Junk Drafts Trash Amazon Later`,
   minus any removed in §4) into `personal/`. **Do not move `.mbsync`.**
5. `mkdir /slowpool/charlie/email/.mbsync/personal` and move the box state files
   into it.
6. Deploy the new role, then run `systemctl start emailbackup@personal.service`.
7. **Verify:** the run pulls ~0 new messages, exits 0, and the file count and `du`
   match the baseline. A large download here means the state files are in the wrong
   place — stop and fix rather than letting it re-fetch 1.5 GB.

Write this as an idempotent guarded script or a `creates:`-guarded task, not a bare
`mv` in a playbook.

---

## 6. The service — `awfulwoman/mail-archive-server`

New repo. Python 3.12+, `uv`, Starlette + uvicorn, stdlib `sqlite3`, stdlib
`email`. No other runtime dependencies.

### 6.1 Configuration

Env vars, prefix `MAIL_ARCHIVE_`:

| Var | Default | Meaning |
|---|---|---|
| `MAIL_ARCHIVE_MAILDIR_PATH` | `/slowpool/charlie/email` | **Root containing account dirs**, read-only |
| `MAIL_ARCHIVE_DB_PATH` | `~/.local/state/mail-archive-server/index.db` | Index (service-owned) |
| `MAIL_ARCHIVE_HOST` | `0.0.0.0` | Bind address |
| `MAIL_ARCHIVE_PORT` | `4103` | Port |
| `MAIL_ARCHIVE_TOKENS__<label>__SECRET` | — | One bearer token; see §6.5 |
| `MAIL_ARCHIVE_TOKENS__<label>__ACCOUNTS` | — | Its account scope: `*` or a CSV list |
| `MAIL_ARCHIVE_EXCLUDE_FOLDERS` | `Trash,Junk` | Default-excluded; see below |
| `MAIL_ARCHIVE_MBSYNC_STATE_PATH` | `{maildir}/.mbsync` | For per-account `last_sync_at` |

Accounts themselves are **not configured here** — they are discovered by walking the
Maildir root (§6.3). Adding an account to the backup makes it appear in the API with
no config change.

`MAIL_ARCHIVE_EXCLUDE_FOLDERS` entries are either a bare folder name (applies to
every account) or `account:folder` (that account only) — different providers name
these folders differently, e.g. `work:[Gmail]/Trash`.

### 6.2 Index schema

```sql
CREATE TABLE IF NOT EXISTS messages (
  id            TEXT PRIMARY KEY,   -- sha256(account||'\0'||folder||'\0'||maildir_name)[:16]
  account       TEXT NOT NULL,      -- 'personal', 'work'
  folder        TEXT NOT NULL,      -- relative to the ACCOUNT dir: 'INBOX', 'Trash/test'
  path          TEXT NOT NULL,      -- absolute; changes when flags change
  maildir_name  TEXT NOT NULL,      -- filename before ':' — stable across flag changes
  message_id    TEXT,               -- Message-ID header, may be ''
  from_name     TEXT,
  from_addr     TEXT,
  from_raw      TEXT,               -- full From header, RFC 2047-decoded
  to_raw        TEXT,
  cc_raw        TEXT,
  subject       TEXT,
  date_utc      TEXT,               -- RFC3339 Z; falls back to file mtime
  size_bytes    INTEGER,
  flags         TEXT,               -- maildir flag letters, e.g. 'S', 'RS', 'ST'
  seen          INTEGER NOT NULL DEFAULT 0,
  deleted       INTEGER NOT NULL DEFAULT 0,  -- maildir 'T' flag; see §6.6
  has_attachment INTEGER NOT NULL DEFAULT 0,
  attachments   TEXT,               -- JSON array, see 6.4
  body_preview  TEXT,               -- first 400 chars of decoded text body
  indexed_at    TEXT NOT NULL,
  mtime         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_account ON messages(account);
CREATE INDEX IF NOT EXISTS idx_msg_date    ON messages(date_utc DESC);
CREATE INDEX IF NOT EXISTS idx_msg_folder  ON messages(account, folder);
CREATE INDEX IF NOT EXISTS idx_msg_from    ON messages(from_addr);
CREATE INDEX IF NOT EXISTS idx_msg_msgid   ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_msg_attach  ON messages(has_attachment);
CREATE INDEX IF NOT EXISTS idx_msg_deleted ON messages(deleted);
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_path ON messages(path);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  id UNINDEXED, subject, from_text, to_text, body,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
```

Open with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`.

Note `message_id` is **not** unique — the same message legitimately appears in
several folders, and across accounts when Charlie is a recipient on both.

Expect ~24k rows today and a few hundred MB of FTS index. Attachment bytes are
never stored.

### 6.3 Indexer

Maildir facts you need:

- Under the root, **each first-level directory is an account**. Skip `.mbsync`.
- Within an account, a mail folder is any directory containing `cur/` and `new/`.
  Walk **recursively** (`SubFolders Verbatim` means `Trash/test/cur` exists).
  Skip `tmp/`.
- `folder` is the path relative to the **account** directory, so `INBOX` and
  `Trash/test` — never including the account name.
- Files in `new/` are **unseen** and have no `:2,` suffix.
- Files in `cur/` are named `<unique>:2,<flags>`; flag letters: `S`=Seen,
  `R`=Replied, `F`=Flagged, `T`=Trashed, `D`=Draft, `P`=Passed. Set `seen` from `S`
  and `deleted` from `T` — the latter is 12% of this archive and must not be
  conflated with the `Trash` folder (§6.6).
- **Flag changes rename the file.** Key on `maildir_name` (the part before `:`),
  never on the full path.
- Ignore `.uidvalidity` and any other dotfile.

Incremental scan:

1. Walk each account, collecting `(account, folder, maildir_name, path, mtime, size)`.
2. Compute `id`. Compare against `messages`:
   - **id absent** → parse fully, insert into `messages` + `messages_fts`.
   - **id present, path unchanged** → skip entirely (no parse).
   - **id present, path changed** → flags changed only. `UPDATE path, flags, seen`.
     **Do not re-parse.**
3. Any id in the DB not seen in the walk → moved or expunged. Delete from both
   tables. **Scope this deletion sweep to the accounts actually walked**, so a
   temporarily unreadable account directory never wipes its rows.
4. Write per-account `last_indexed_at` into `meta`.

Only branch one touches bodies, so a steady-state reindex after an hourly mbsync
run is near-free.

**Attachment detection** — this is the feature that motivated the project, so get
it exactly right. Walking `msg.walk()`, a part is an attachment when either:

- `part.get_content_disposition() == "attachment"`, **or**
- `part.get_filename()` is not `None` **and** its content type is not `text/plain`
  or `text/html`.

Never count `multipart/*` containers. `message/rfc822` **does** count. Record each
attachment's `content_disposition` so callers can distinguish inline images from
true attachments, and set `has_attachment` from the rule above.

Body extraction: prefer the first `text/plain` part, else the first `text/html`.
Decode with `errors="replace"` (mirrors `gateway/tools/email.py:50`). Decode
headers with `email.header.decode_header` / `email.utils.parseaddr` — see §2.5.

Run the indexer at startup, on `POST /reindex`, and from a systemd unit ordered
after the backup units (§7). Guard with a lock so two scans never overlap; report
`"indexing": true` in `/status` while one runs. `POST /reindex` accepts an optional
`account` to rescan just one.

### 6.4 HTTP API

All endpoints except `/health` require `Authorization: Bearer <token>`; missing or
unknown → **401**. Every endpoint is additionally **scoped to the token's accounts**
(§6.5). Errors use the shape already established across this estate:

```json
{"error": {"code": "not_found", "message": "no such message"}}
```

```
GET  /health                 no auth -> {"status": "ok"}
GET  /status                 index + sync freshness, per account
GET  /accounts               account list with counts
GET  /folders                folder list with counts (filterable by account)
GET  /messages               search / filter  (the main endpoint)
GET  /messages/{id}          one message, including full body
POST /reindex                incremental scan -> 202 {"indexing": true}
```

**`GET /messages` query parameters**

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — | FTS5 MATCH over subject/from/to/body |
| `account` | string, repeatable | — | omit for **all accounts** |
| `exclude_account` | string, repeatable | — | |
| `from` | string | — | substring on `from_raw` |
| `to` | string | — | substring on `to_raw` |
| `subject` | string | — | substring on `subject` |
| `folder` | string, repeatable | — | exact; matches in any selected account |
| `exclude_folder` | string, repeatable | `Trash`,`Junk` | pass empty to include them |
| `since` / `until` | ISO date or RFC3339 | — | on `date_utc`, inclusive |
| `has_attachment` | bool | — | omit for "don't care" |
| `attachment_name` | string | — | substring over indexed filenames |
| `seen` | bool | — | as of last sync — see §8.3 |
| `include_deleted` | bool | `false` | retained deleted mail — see §6.6 |
| `limit` | int | 25 | max 200 |
| `offset` | int | 0 | |
| `order` | enum | `date_desc` | `date_desc`\|`date_asc`\|`relevance` |

`relevance` is valid only with `q`; otherwise 400. An unknown `account` is a 400,
not an empty result — silently returning nothing hides typos.

**Response**

```json
{
  "messages": [ /* summary objects */ ],
  "total": 137,
  "limit": 25,
  "offset": 0,
  "accounts_searched": ["personal", "work"],
  "index": {
    "last_indexed_at": "2026-09-04T18:02:00Z",
    "oldest_sync_at": "2026-09-04T00:03:24Z",
    "stale_seconds": 64716
  }
}
```

`stale_seconds` is the **worst** (largest) value across the accounts actually
searched — a result set is only as fresh as its stalest source.

**Summary object** — the key names `from`, `subject` and `date` are **required
exactly as spelled**, because `gateway/cli/fmt.py:63-72` reads them and must keep
working unchanged:

```json
{
  "id": "a1b2c3d4e5f60718",
  "account": "personal",
  "message_id": "<CAF...@mail.example.com>",
  "folder": "INBOX",
  "from": "Alice Smith <alice@example.com>",
  "from_addr": "alice@example.com",
  "to": "charlie@example.com",
  "subject": "Invoice for August",
  "date": "2026-09-01T09:15:04Z",
  "seen": true,
  "deleted": false,
  "size_bytes": 91234,
  "has_attachment": true,
  "attachments": [
    {"filename": "invoice.pdf", "content_type": "application/pdf",
     "size_bytes": 88213, "content_disposition": "attachment"}
  ],
  "body_preview": "Hi Charlie, please find attached…"
}
```

`GET /messages/{id}` returns the same object plus `"body"`.

**`GET /accounts`**

```json
{"accounts": [
  {"name": "personal", "messages": 24404, "folders": 8, "unseen": 387,
   "last_sync_at": "2026-09-04T00:03:24Z", "last_indexed_at": "2026-09-04T18:02:00Z",
   "stale_seconds": 64716}
]}
```

**`GET /status`** — top level plus a per-account breakdown, since one account can be
stale or failing while another is fresh:

```json
{
  "maildir_path": "/slowpool/charlie/email",
  "messages": 24404,
  "accounts": [ /* as above */ ],
  "stale_seconds": 64716,
  "indexing": false
}
```

Derive each account's `last_sync_at` from the newest mtime under
`{MAIL_ARCHIVE_MBSYNC_STATE_PATH}/{account}/`.

### 6.5 Token scoping — the security boundary

The service serves **all accounts by default**, so the bearer token is what decides
which mail a caller can reach. This must be enforced **server-side**. A client-side
allowlist (§8.1) is an ergonomics filter and is worth nothing as a control — anything
holding the token could simply ask for the other accounts.

Tokens are configured as labelled entries, mirroring the account map Gateway uses
(§8.1) so both repos read the same way:

```
MAIL_ARCHIVE_TOKENS__gateway__SECRET=…
MAIL_ARCHIVE_TOKENS__gateway__ACCOUNTS=*
MAIL_ARCHIVE_TOKENS__scratch__SECRET=…
MAIL_ARCHIVE_TOKENS__scratch__ACCOUNTS=personal
```

`ACCOUNTS=*` means every account present in the Maildir, **including ones added
later** — that is the point of discovery. A CSV list pins the scope; a name in it
that never appears in the Maildir is a startup warning, not an error (the backup may
not have run yet).

The label is for operator legibility only; it never appears in a response.

**Enforcement, at every endpoint:**

| Situation | Result |
|---|---|
| Missing or unknown token | 401 |
| `GET /accounts`, `/folders`, `/status` | list **only** in-scope accounts |
| `GET /messages` with no `account` | implicitly restricted to in-scope accounts |
| `GET /messages` naming an out-of-scope account | **403**, `"code": "account_forbidden"` |
| `GET /messages/{id}` for an out-of-scope message | **404** — ids are opaque, do not confirm existence |
| `POST /reindex` | requires a `*`-scoped token; otherwise 403 |

Scope filtering belongs in the query layer, applied to every account-touching query
as a mandatory predicate — not bolted on per handler, where the next endpoint added
will forget it. Prefer a single choke point that takes the caller's scope and refuses
to build a query without one.

403 rather than an empty result for a named out-of-scope account is deliberate: it
tells an operator their token is too narrow, instead of a model concluding the mail
does not exist. It does leak that the *name* was rejected, which is acceptable —
account names are not secrets, their contents are.

Test scope enforcement in the service's **own** test suite, endpoint by endpoint,
with a narrowly-scoped token. A scope bug is the one defect in this document that
loses mail to a caller who should not have it, and it cannot be caught from
Gateway's tests.

### 6.6 Deleted-but-retained mail — the `T` flag

`Expunge None` (§2.1) means mail expunged server-side is **flagged**, not removed,
locally. Per `man mbsync`, `Sync` defaults to `All`, which includes `Delete`:
deletions propagate to the near side, and `Expunge None` then declines to actually
remove them. On disk they are ordinary Maildir files carrying the `T` flag
(`…:2,ST`, `…:2,FST`).

Measured on the live archive, 2026-09-04:

| | |
|---|---|
| `T`-flagged messages | **3,210** of 26,943 — **12% of the corpus** |
| Where they live | **3,205 in `INBOX`**, 1 in `Sent`, **0 in `Trash`** |

**This is why the `exclude_folder` default is not sufficient.** Excluding `Trash` and
`Junk` catches *none* of these — they sit in INBOX, interleaved with live mail. Left
unhandled, one in eight search results is mail Charlie deliberately deleted, with
nothing to distinguish it.

So `deleted` is a first-class indexed column, derived from the `T` flag, and
`include_deleted` defaults to **false** on `GET /messages`. Every returned object
carries `"deleted"` so a caller that opts in can still tell them apart. Deleted mail
stays indexed and retrievable by id — the point is that it is *opt-in*, not that it
is hidden.

This is also the answer to "should `Expunge None` change?" — see §6.7.

### 6.7 Why `Expunge None` stays

It is reasonable to ask whether ZFS snapshots make `Expunge None` redundant. They do
not — but the reason is *not* thin retention, which is what one might assume.
Verified on the pool and in `inventory/host_vars/server-64gb-storage/core.yaml:137`:

| | |
|---|---|
| Snapshot policy | **`critical`** — the highest tier: 36 hourly, 30 daily, 3 monthly, **5 yearly** |
| Currently on disk | 37 hourly, 30 daily, 3 monthly, **0 yearly** |
| Why 0 yearly | Dataset created 2026-02-09; the yearly timer is `*-01-01`, so the first accrues 2027-01-01 |
| Cost | `usedbysnapshots` **37.5 MB** against a 1.42 GB dataset |
| Second copy | Pulled to `server-8gb-backups` by `backups-zfs-server` (recursive, so this dataset is included) |
| Offsite | **`backups_zfs_server_offsite_enabled: false`** — no offsite leg for *any* dataset |

Retention is therefore genuinely long-term *by policy*, though multi-year coverage
does not exist **yet** — nothing older than 2026-07-01 is recoverable today.

Three reasons snapshots still do not substitute:

1. **Snapshots are not searchable.** This is the decisive one. Recovery means
   guessing roughly *when* it was deleted, mounting `.zfs/snapshot/<name>/`, and
   finding one file among 27,000. With `Expunge None` plus this service, it is
   `include_deleted=true` and a query. Beyond 30 days the only granularity is
   monthly, so "which snapshot" becomes a real guess.
2. **Different failure modes.** Snapshots protect against corruption or a bad mbsync
   run mangling the Maildir — recovery is a rollback. `Expunge None` protects against
   *you* deleting something you later want — recovery is a search. Neither covers the
   other.
3. **Changing it is destructive and near-irreversible.** Switching `Expunge` to
   `Near` or `Both` permanently removes those 3,210 messages on the next run.

The cost of keeping it is negligible (37.5 MB of snapshot overhead; the retained
messages are a fraction of 1.42 GB), and the problem it actually caused was search
pollution, which §6.6 fixes directly. So: **keep `Expunge None`.**

One genuine follow-up, not blocking this work: offsite replication is disabled
estate-wide, so every dataset including this one has a second copy on the backups
host but no offsite copy. Tracked separately.

---

## 7. Infra — `awfulwoman/infra`

### 7.1 New role `roles/system-mail-archive-server/`

Model it on `roles/system-apple-reminders-server/`, but **drop** everything
macOS-specific (the `Assert macOS`, Homebrew, code-signing and LaunchAgent tasks).
Keep the repo clone/update pattern and the token wiring.

- Assert `ansible_facts['os_family'] == 'Debian'`.
- Clone/update `awfulwoman/mail-archive-server` into
  `{{ system_repos_base_dir }}/awfulwoman/mail-archive-server`; `uv sync`.
- Verify the Maildir root exists, failing fast — copy the `system-emailbackup`
  stat/fail idiom (`roles/system-emailbackup/tasks/main.yaml:8-17`).
- Template an env file + `mail-archive-server.service` (systemd, `Type=simple`,
  `User={{ ansible_user }}`, `Restart=on-failure`).
- Template `mail-archive-reindex.service` (`Type=oneshot`, curls `POST /reindex`)
  plus a timer running shortly after the backup timers. Do **not** chain it to a
  single `emailbackup.service` — there is now one unit per account (§5.4).
- Defaults mirroring the reminders role, including
  `system_mail_archive_server_bearer_tokens: "{{ vault_gateway_mail_archive_server_token }}"`.

Register in `playbooks/hosts/server-64gb-storage/core.yaml` immediately after
`system-emailbackup`, tagged `[system, system-mail-archive-server]`.

### 7.2 Vault

Add `vault_gateway_mail_archive_server_token` — the secret behind the archive's
`gateway`-labelled token (§6.5), scoped `*`. Issue a separate, narrower token for any
other client rather than sharing this one; that is the only way to actually restrict
what a client can read.

Additional mail accounts need their own `vault_…` credential entries referenced from
the shared account list below.

### 7.3 One account list, two consumers

`system-emailbackup` and `composition-gateway` must never disagree about account
names (contract §10.16). Define the list **once** in
`inventory/host_vars/server-64gb-storage/core.yaml` and have both roles read it:

```yaml
charlie_email_accounts:
  - name: personal
    imap_host: "imap.{{ vault_mailprovider_domain }}"
    imap_user: "{{ vault_mailprovider_user }}"
    imap_password: "{{ vault_mailprovider_password }}"
  # - name: work
  #   imap_host: imap.example.com
  #   imap_user: "{{ vault_work_mail_user }}"
  #   imap_password: "{{ vault_work_mail_password }}"

emailbackup_accounts: "{{ charlie_email_accounts }}"
composition_gateway_imap_accounts: "{{ charlie_email_accounts }}"
composition_gateway_imap_default_account: personal
```

Adding an account is then one edit in one place.

### 7.4 `roles/composition-gateway`

`defaults/main.yaml` — follow the existing lines at `:33`, `:53`, `:61`. The service
is on the *same* host as the container, so this must be the host's own address,
**not** `localhost` (which inside the container is the container):

```yaml
composition_gateway_mail_archive_server_base_url: "http://{{ hostvars[inventory_hostname]['host_fqdn'] }}:4103"
composition_gateway_mail_archive_server_bearer_token: "{{ vault_gateway_mail_archive_server_token }}"
composition_gateway_mail_archive_server_accounts: []   # empty = all in token scope
composition_gateway_imap_accounts: []
composition_gateway_imap_default_account: ""
```

Leave `..._accounts` empty in normal operation — Gateway discovers what its token
allows. Set it only to deliberately narrow Gateway to fewer mailboxes than the token
permits; to actually *deny* access, narrow the token's scope instead (§6.5).

`templates/environment_vars.j2` — **remove** the four legacy `GATEWAY_IMAP__*` lines
(`:5-8`) and emit a block per account instead:

```jinja
{% for acct in composition_gateway_imap_accounts %}
GATEWAY_IMAP_ACCOUNTS__{{ acct.name }}__HOST={{ acct.imap_host }}
GATEWAY_IMAP_ACCOUNTS__{{ acct.name }}__PORT={{ acct.imap_port | default(993) }}
GATEWAY_IMAP_ACCOUNTS__{{ acct.name }}__USERNAME={{ acct.imap_user }}
GATEWAY_IMAP_ACCOUNTS__{{ acct.name }}__PASSWORD={{ acct.imap_password }}
{% endfor %}
GATEWAY_IMAP_DEFAULT_ACCOUNT={{ composition_gateway_imap_default_account }}

GATEWAY_MAIL_ARCHIVE_SERVER__BASE_URL={{ composition_gateway_mail_archive_server_base_url }}
GATEWAY_MAIL_ARCHIVE_SERVER__BEARER_TOKEN={{ composition_gateway_mail_archive_server_bearer_token }}
GATEWAY_MAIL_ARCHIVE_SERVER__ACCOUNTS={{ composition_gateway_mail_archive_server_accounts | join(',') }}
```

Only the **IMAP** block loops over accounts — the archive block does not, because
Gateway discovers those (§8.1).

Account names reach Gateway inside env-var *names*. Hyphens are fine here — the
container is configured through `env_file: .environment_vars`, not shell exports —
but see the naming contract in §10.16.

**Do not add a volume mount to `docker-compose.yaml.j2`.** Reaching the Maildir over
HTTP instead of a bind mount is the whole point of this design.

---

## 8. Gateway — `awfulwoman/gateway`

> **Read §0 before this section.** The live-IMAP path below (per-account IMAP
> credentials in Gateway, IMAP fallback, `searchable`/`live` split) was dropped on
> 2026-09-29. Everything goes through the archive.

### 8.1 Config — the account model

Gateway deals with accounts on **two different paths**, and they are configured
differently on purpose:

| Path | How Gateway learns the accounts | Why |
|---|---|---|
| Archive (search, list, folders) | **Discovered** from `GET /accounts` | Needs no secrets — the token already scopes it |
| Live IMAP (unread, mark-read) | **Configured**, per account | Needs credentials, which cannot be discovered |

So the archive account list is never duplicated in Gateway config. Adding a mailbox
to the backup makes it searchable through Gateway with no Gateway change at all.

**Archive path.** `MailArchiveServerConfig` gains an optional allowlist:

```python
class MailArchiveServerConfig(BaseModel):
    """mail-archive-server on the storage host — indexed, multi-account search over
    the mbsync Maildir backup. Read-only; IMAP remains the backend for unread state
    and writes (see gateway/tools/email.py).

    `accounts` is an optional ERGONOMIC filter — leave it empty to use every account
    the bearer token can see. It is not a security control: the token's server-side
    scope is (see the handoff spec §6.5)."""
    base_url: str = ""
    bearer_token: str = ""
    accounts: Annotated[list[str], NoDecode] = []   # empty = all in-token-scope
```

Use the existing `_split_csv` + `@field_validator(mode="before")` idiom already used
for `RemindersConfig.api_tokens` and `ServerConfig.auth_tokens`. Env form:
`GATEWAY_MAIL_ARCHIVE_SERVER__ACCOUNTS=personal,work`.

Discover accounts lazily on first use and cache for ~60s; do **not** call
`GET /accounts` on every tool invocation, and do **not** fetch it at startup — the
archive being briefly down must not stop Gateway booting. If `accounts` names
something the token cannot see, raise on first use naming the mismatch, rather than
silently returning nothing.

**Live IMAP path.** `gateway/config.py` currently holds a **single** `IMAPConfig`.
Replace it with a map of named accounts whose keys are the **same names** used by
`emailbackup_accounts` and reported by the archive's `account` field.

```python
class IMAPAccountConfig(BaseModel):
    """One IMAP mailbox. The key this is stored under in Config.imap_accounts is the
    account name, and must match the archive's `account` values (see the handoff
    spec §10.16) — the same name identifies a mailbox in the backup, the archive
    API, and here."""
    host: str = "imap.mailbox.org"
    port: int = 993
    username: str = ""
    password: str = ""


class MailArchiveServerConfig(BaseModel):
    """mail-archive-server on the storage host — indexed, multi-account search over
    the mbsync Maildir backup. Read-only; IMAP remains the backend for unread state
    and writes (see gateway/tools/email.py)."""
    base_url: str = ""
    bearer_token: str = ""
```

On `Config`, **replace** `imap: IMAPConfig` with:

```python
    imap_accounts: dict[str, IMAPAccountConfig] = {}
    imap_default_account: str = ""
    mail_archive_server: MailArchiveServerConfig = MailArchiveServerConfig()
```

`imap_accounts` may legitimately be a **subset** of the archive's accounts — see the
divergence rules in §8.3. Configuring credentials for a mailbox you only ever want to
search is unnecessary work.

**Verified working** against pydantic-settings 2.14.0 / pydantic 2.13.3 with the
existing `env_prefix="GATEWAY_"` and `env_nested_delimiter="__"` — no custom
parsing needed. Env var form, one block per account:

```
GATEWAY_IMAP_ACCOUNTS__personal__HOST=imap.mailbox.org
GATEWAY_IMAP_ACCOUNTS__personal__PORT=993
GATEWAY_IMAP_ACCOUNTS__personal__USERNAME=charlie@example.com
GATEWAY_IMAP_ACCOUNTS__personal__PASSWORD=…
GATEWAY_IMAP_ACCOUNTS__work__HOST=imap.example.com
GATEWAY_IMAP_ACCOUNTS__work__USERNAME=…
GATEWAY_IMAP_ACCOUNTS__work__PASSWORD=…
GATEWAY_IMAP_DEFAULT_ACCOUNT=personal
```

Per-account field defaults apply normally (an omitted `PORT` yields 993), keys keep
their case, and hyphenated names load correctly from an env file.

**Cutover, not compatibility shim.** `GATEWAY_IMAP__*` is removed in the same change
that adds the above; the Ansible template (§7.4) is updated in lockstep. To make a
half-migrated deployment fail loudly instead of silently losing an account, validate
at startup and **raise**:

- `imap_default_account` unset while more than one account is configured, or set to
  a name absent from `imap_accounts` → list the valid names.
- any legacy `GATEWAY_IMAP__*` var still present in the environment → say it is
  superseded and show the replacement.

**Warn**, do not raise, when `imap_accounts` is empty: search still works, so this is
a valid search-only deployment. The IMAP-backed tools then raise when actually
called, naming the env var form they need.

With exactly one account, `imap_default_account` may be omitted and that account is
implicitly the default.

### 8.2 Client

New package `gateway/mail_archive_server/` (`__init__.py`, `store.py`). Copy the
shape of `gateway/contacts_server/store.py:1-18` verbatim — module-level `_config`
and `_client`, `init()` building an `httpx.Client` with the bearer header and
`timeout=10.0`, and an `_error_message(response)` helper.

Functions: `search(**params) -> dict`, `get_message(id) -> dict | None` (404 →
`None`), `accounts() -> list[dict]`, `folders(account=None) -> list[dict]`,
`status() -> dict`.

### 8.3 Tools — the source split

`gateway/tools/email.py`. **This split is the contract; do not blur it.**

| Tool | Backend | `account=None` means |
|---|---|---|
| `search_emails` | archive | all accounts |
| `list_emails` | archive | all accounts |
| `list_folders` | archive | all accounts, account-qualified |
| `list_email_accounts` (new) | config + archive | — |
| `email_archive_status` (new) | archive | all accounts |
| `fetch_email_body` | archive, IMAP fallback | resolve by id; see below |
| `fetch_unread_emails` | **IMAP** | **fan out to all accounts** |
| `mark_email_read` | **IMAP** | default account; see below |

`init(imap_accounts, imap_default_account, mail_archive_config)` — update the call
site at `gateway/main.py:56`.

**When the two account sets diverge.** The archive's accounts (discovered, §8.1) and
`imap_accounts` (configured) need not match. Both directions are legitimate and must
behave predictably:

| Case | Behaviour |
|---|---|
| In archive, **not** in `imap_accounts` | Searchable. `fetch_unread_emails` / `mark_email_read` raise a clear "no IMAP credentials configured for account X" |
| In `imap_accounts`, **not** in archive | Live tools work. Search cannot see it; say so rather than implying the mailbox is empty |
| In both | Everything works |

`list_email_accounts` must report, per account, which capabilities it actually has —
`searchable` and `live` as separate booleans. The model needs this to avoid promising
an operation that will fail.

**Account resolution rules** — apply these uniformly:

- **Read and search tools:** `account=None` means *all* accounts. Never silently
  narrow to the default; a search that quietly covered one of three mailboxes is
  the failure mode this whole change exists to remove.
- **Writes (`mark_email_read`):** never fan out. Resolve in this order — an explicit
  `account` argument; else the `account` carried on the archive result the caller is
  acting on; else `imap_default_account`. If more than one account is configured and
  none of those resolve, raise rather than guess.
- **Unknown account name:** raise, listing the valid names. Never return an empty
  result set — that reads to the model as "no such mail exists".
- Every returned message object carries its `"account"`, so the model can pass it
  back to a write tool.

**Fan-out behaviour** for `fetch_unread_emails`: query each configured account,
merge, sort `date` descending, then apply `max_count` across the merged set. Open
connections per account (they are separate servers); a **partial failure must not
fail the call** — return what succeeded plus an `"errors": [{"account": …,
"message": …}]` array, so one broken mailbox cannot blind the model to the others.

**Per-account IMAP connections:** `_connection(folder, account)` looks the account up
in the config map and raises a clear error for an unknown name. Keep the
`contextmanager` shape at `gateway/tools/email.py:16-28`.

**Graceful degradation:** wrap archive calls; on `httpx` error fall back to the IMAP
implementation (keep it, do not delete it), fanning out across accounts the same
way. Every result gains `"source": "archive" | "imap"`; archive results carry
`"stale_seconds"`. If a fallback or a partial failure means fewer accounts were
searched than requested, say which ones were covered — a silently partial answer is
worse than a slow one.

**`search_emails`** gains `account`, `has_attachment: bool | None = None`, `since`,
`until`, `folder`. Keep `query`, `search_in` and `max_results` working so the
existing MCP surface and CLI do not break; map `search_in` → `q`/`from`/`subject`.

**`fetch_email_body`** prefers the archive `id` (globally unique). `message_id` is
**not** unique across accounts (§10.7), so when given one, accept an optional
`account`; if it matches in several accounts and none was named, return the matches
with their accounts and ask for disambiguation rather than picking one.

**`list_email_accounts`** returns each account with its archive counts, staleness, and
the `searchable` / `live` capability booleans above, so the model knows the valid
`account` values — and what it can do with each — without guessing.

Docstrings are the MCP tool descriptions. State in `search_emails`' docstring that
results come from a periodically-synced archive, may lag, span all accounts by
default, and that unread status must be checked with `fetch_unread_emails`.

### 8.4 CLI

`gateway/cli/commands/email.py` — add `--account` to `search`, `list`, `folders` and
`unread` (omitted = all accounts); add `--has-attachment/--no-attachment`
(tri-state, default `None`), `--since` and `--until` to `search`; add `--account` to
`mark-read` (omitted = default account). Add `gw email accounts` and
`gw email status`. Follow the existing `client.call_tool` + `GatewayError` →
`ClickException` idiom used by every command in that file.

`gateway/cli/fmt.py` — `emails()` (`:63-72`) needs no change if §6.4's key names are
honoured. Add an `account` column **only when the result set spans more than one
account**, so single-account output stays as terse as it is today, and a `📎` marker
when `has_attachment` is true.

### 8.5 Tests

`tests/conftest.py` — add `_FakeMailArchiveServer` and a session-scoped
`mail_archive_server` fixture, mirroring `_FakeContactsServer` (`:327-421`) exactly:
in-process uvicorn thread on a free port, storage keyed by bearer token for
per-test isolation, `_free_port()`, the 100×0.05s startup poll. Seed it with **two
accounts**. Add a fake IMAP double covering **two accounts** so the fan-out paths
are exercised.

`tests/test_email.py` (new) — cover at minimum:

- `has_attachment=True` returns only messages with attachments; `False` only those
  without; omitted returns both.
- `account=None` spans both accounts **discovered from the fake server**, with
  neither named in Gateway config; `account="work"` restricts correctly; an unknown
  account **raises** rather than returning an empty list.
- A non-empty `MailArchiveServerConfig.accounts` allowlist narrows the searched set;
  naming an account the token cannot see raises on first use.
- Account discovery is cached, not re-fetched per call, and a `GET /accounts` failure
  at startup does not prevent Gateway starting.
- Divergence: an account present in the archive but absent from `imap_accounts` is
  searchable, reports `live=false`, and raises a credentials error from
  `fetch_unread_emails` rather than returning an empty inbox.
- The same `message_id` present in two accounts yields two distinct `id`s, and
  `fetch_email_body` by that `message_id` without an `account` asks for
  disambiguation instead of guessing.
- `fetch_unread_emails` merges both accounts, sorts by date desc, and applies
  `max_count` across the merged set.
- **One account's IMAP failing still returns the other's unread mail, plus a
  populated `errors` array.**
- `mark_email_read` never fans out: with two accounts and no resolvable account it
  raises; given an `account` it writes only there.
- `search_in` values still map correctly; `since`/`until` are inclusive.
- Missing/invalid bearer token → 401 surfaces as a clean error.
- **Archive unreachable → falls back to IMAP, marks `"source": "imap"`, and still
  covers every account.**
- `stale_seconds` reflects the **stalest** account in a multi-account result.
- Config validation: an `imap_default_account` naming a missing account and a
  leftover `GATEWAY_IMAP__*` var each raise at startup with a message naming the fix;
  an empty `imap_accounts` only warns.

`tests/cli/test_email.py` — update for the new flags; assert the `account` column
appears only in multi-account output.

`.env.example` — replace the four `GATEWAY_IMAP__*` lines with the per-account form
from §8.1, showing two accounts and `GATEWAY_IMAP_DEFAULT_ACCOUNT`.

---

## 9. Acceptance

Run in order; each must pass before moving on.

1. **Backup healthy.** `systemctl start emailbackup@personal.service` exits 0 and
   `systemctl is-failed` reports `no`. Per §4.1 this would be the **first recorded
   success**, so treat a green run as a real milestone, not a formality.
2. **Failure is actually reported.** Deliberately fail a run (point an account at a
    bad host) and confirm the `OnFailure=` notification arrives and names the
    account. Until this passes, every other check here is unverifiable in production.
3. **Stale folders no longer accumulate.** With `Remove Near`, delete a scratch
    remote folder and confirm the next run exits 0 and removes the empty local copy.
    Repeat with a *non-empty* local copy and **record** whether it errors (§4.3) —
    that answer belongs in the role README.
4. **Migration was free.** After §5.5, the first post-migration run pulls ~0 new
   messages and the file count and `du -sh` match the pre-migration baseline.
5. **Account isolation.** Break one account deliberately (bad password in a scratch
   second account); its unit fails and `personal`'s still succeeds.
6. **Index builds.** Cold `POST /reindex` over ~24k messages completes; row count is
   within a few of the on-disk message-file count, and `account` is populated on
   every row.
7. **Reindex is cheap.** A second immediate reindex parses **zero** new messages and
   completes in a few seconds.
8. **Flag churn is cheap.** Toggle a message's Seen flag (rename its file in `cur/`),
   reindex: `path`/`flags`/`seen` update and no re-parse occurs.
9. **Attachments are correct.** Pick 10 messages by hand across folders — 5 with real
   attachments, 5 with inline images or none. `has_attachment` matches human
   judgement on all 10. This is the feature that motivated the project.
10. **Search works.** `q` ranks sensibly; `since`/`until` inclusive; `exclude_folder`
   defaults keep `Trash`/`Junk` out; `account` filters correctly and omitting it
   spans all.
11. **Deleted mail is excluded by default.** A default search returns no `T`-flagged
   messages — on this archive that is ~3,210 messages, nearly all in **INBOX**, so a
   naive implementation fails this loudly. `include_deleted=true` returns them, each
   marked `"deleted": true`, and they stay fetchable by id either way.
12. **Auth.** No token and a wrong token both return 401; `/health` works without.
13. **Token scope is enforced server-side.** With a token scoped to `personal` only:
    `GET /accounts` lists just `personal`; `GET /messages` with no `account` returns
    only `personal` mail; `GET /messages?account=work` returns **403**, not an empty
    list; a `work` message fetched by id returns **404**; `POST /reindex` returns
    403. Confirm this by calling the API **directly with curl**, not through Gateway
    — the point is that a client cannot talk its way past the scope.
14. **New accounts appear without config changes.** Add a third account to the
    backup; a `*`-scoped token sees it in `GET /accounts` after a reindex, with no
    edit to the service's or Gateway's configuration.
15. **Gateway end-to-end.** `gw email search invoice --has-attachment` returns rows,
    `gw email accounts` lists them, `gw email status` shows plausible per-account
    `stale_seconds`.
16. **Gateway spans accounts.** With two accounts in the backup, `gw email search`
    with no `--account` returns hits from **both** — *without* either being listed in
    Gateway's config. `gw email unread` merges both inboxes. `--account work` narrows
    correctly.
17. **Capabilities are reported honestly.** Configure IMAP credentials for only one
    of the two accounts. `gw email accounts` shows `searchable=true, live=true` for
    it and `searchable=true, live=false` for the other, and `gw email unread
    --account <the other>` fails with a message naming the missing credentials — not
    an empty inbox.
18. **Names line up.** The account names in `gw email accounts` match
    `emailbackup_accounts[].name`, the directory names under
    `/slowpool/charlie/email/`, and the systemd instances — one set of names, no
    aliasing.
19. **Partial IMAP failure degrades gracefully.** Point one account at a bad
    password; `gw email unread` still returns the healthy account's mail and reports
    the failure rather than erroring out.
20. **Degradation.** Stop the archive service; `gw email search` still works via
    IMAP, reports `"source": "imap"`, and still covers every account.
21. **Statelessness.** `docker-compose.yaml.j2` has gained no volume, Gateway writes
    nothing to disk, and `pytest` passes.

---

## 10. The contract — what you must not get wrong

1. **Gateway owns nothing.** No mount, no index, no Maildir parsing in Gateway. If
   you find yourself adding a volume to the compose template, stop.
2. **Read-only on mail.** The service never writes to the Maildir. Mount it
   read-only where possible; never open a message file for writing.
3. **Per-account `SyncState` directories.** State files are box-named with no channel
   prefix (§2.2); a shared directory silently corrupts sync across accounts.
4. **Migrate by moving state files, not by re-syncing.** A migration that
   re-downloads 1.5 GB is a failed migration.
5. **Key on `account` + `folder` + `maildir_name`, not path.** Flag changes rename
   files; keying on path makes every flag change look like a delete plus an insert.
6. **`folder` excludes the account name.** `INBOX`, not `personal/INBOX`.
7. **`message_id` is not unique** — not across folders, not across accounts. The
   archive `id` is the only globally unique handle.
8. **Unread state stays on IMAP** — the archive's `seen` is as of last sync and is
   offered for filtering, not as truth.
9. **`account=None` means *all* accounts on every read path,** and never on a write
   path. Silently narrowing a search to one mailbox is the exact failure this change
   exists to remove; silently fanning out a write is worse.
10. **Never return empty for an unknown or forbidden account** — raise, or 403, and
    list the valid names. An empty result reads to the model as "no such mail
    exists".
11. **The token is the security boundary, not the client allowlist.**
    `GATEWAY_MAIL_ARCHIVE_SERVER__ACCOUNTS` is ergonomics; scope enforcement lives in
    the service's query layer (§6.5). Never implement an access restriction only in
    Gateway.
12. **Accounts are discovered, not declared.** The archive's account list comes from
    the Maildir; Gateway learns it from `GET /accounts`. Adding a mailbox must not
    require editing Gateway config. Only IMAP *credentials* are configured.
13. **Always surface coverage and staleness.** Report the **worst** account's
    staleness for a multi-account result, and say which accounts a partial or
    fallback answer actually covered.
14. **Local is a superset of the mailbox**, in two independent ways: whole folders
    the server no longer has, and `T`-flagged messages the server expunged (12% of
    this corpus, nearly all in INBOX). `exclude_folder` handles the first;
    `include_deleted=false` handles the second. Neither covers the other (§6.6).
15. **Preserve the `from`/`subject`/`date` key names** so `cli/fmt.py` keeps working.
16. **Account names are a shared contract** across `charlie_email_accounts[].name`,
    the Maildir directory, the systemd instance, the archive API's `account` field,
    and Gateway's `GATEWAY_IMAP_ACCOUNTS__<name>__*` env keys. One name, everywhere,
    matching `^[a-z0-9][a-z0-9_-]*$`. Defined once (§7.3) so it cannot drift.
17. **No autonomous LLM behaviour** (Gateway `CLAUDE.md`). This service makes no model
    calls; the reindex trigger is a deterministic systemd unit.
18. **Do not expose 4103 publicly.** Bearer token on every endpoint, LAN/Tailscale
    only, no Traefik router.

---

## 11. Suggested order of work

1. §4 mbsync fix. Independently valuable; ship it alone.
2. §5 multi-account role + migration, still with one account. Prove §9.1–9.5 before
   adding a second account — the migration is the riskiest step in this document.
3. §8.1 Gateway account model + §7.3/§7.4 env template, still with one account.
   A pure refactor with no behaviour change, so it lands safely on its own and
   takes the config churn off the critical path.
4. `mail-archive-server` repo: schema → indexer → API, with tests against a small
   **two-account** fixture Maildir committed to that repo. Build token scoping
   (§6.5) **with** the endpoints, not as a later pass — retrofitting a scope
   predicate onto handlers that already work is how one gets missed.
5. Ansible role; deploy; verify §9.6–9.14 against the real archive, including the
   curl-level scope checks.
6. Gateway client + tools + CLI + tests (§9.15–9.21).
7. Add the second real account — one edit to `charlie_email_accounts` (§7.3) — and
   re-run §9.16–9.19.
8. Deploy Gateway per `.claude/rules/deploy.md` — push to `main`, then run
   `playbooks/hosts/server-64gb-storage/core.yaml` with tag `composition-gateway`.

Steps 1–3 and step 4 are independent and can run in parallel. Step 6 must not merge
before step 5 is deployed, or `search_emails` will fall back to IMAP in production —
correct behaviour, but it would mask a broken rollout. Leave step 7 until the
single-account path is green end to end; adding a mailbox should then be a one-line
change, and if it is not, something earlier in the chain hardcoded an assumption.
