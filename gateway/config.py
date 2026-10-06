from typing import Annotated
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(v):
    return [t.strip() for t in v.split(",") if t.strip()] if isinstance(v, str) else v


class MailArchiveServerConfig(BaseModel):
    """mail-archive-server — the sole holder of mail credentials; Gateway
    holds none (handoff spec §0's decisions, superseding §8.1's original
    per-account IMAPConfig design). `accounts` is an ergonomic filter only
    (empty = every account the bearer token can see) — never a security
    control, the token's own server-side scope is that."""
    base_url: str = ""
    bearer_token: str = ""
    accounts: Annotated[list[str], NoDecode] = []

    @field_validator("accounts", mode="before")
    @classmethod
    def _split_accounts(cls, v):
        return _split_csv(v)


class ObsidianConfig(BaseModel):
    vault_path: str = ""


class GitHubConfig(BaseModel):
    """Backs the issues tools, which call the GitHub REST API directly. `repo` is
    owner/name; `token` is a PAT with issues read/write on that repo, supplied as
    GATEWAY_GITHUB__TOKEN."""
    repo: str = "awfulwoman/meta"
    token: str = ""


class CalendarServerConfig(BaseModel):
    """apple-calendar-server on Malcolm — real Apple Calendar via EventKit,
    replacing Google Calendar as gateway's calendar backend."""
    base_url: str = ""
    bearer_token: str = ""


class EbayConfig(BaseModel):
    """Backs the eBay tools, which call eBay's Browse API directly with an
    application (client-credentials) token — no eBay user login involved.
    Keys come from a production keyset at developer.ebay.com. `marketplace`
    is used when the input carries no domain to infer one from (a bare item
    ID, or a search)."""
    client_id: str = ""
    client_secret: str = ""
    marketplace: str = "EBAY_DE"


class KarakeepConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""


class OwnTracksConfig(BaseModel):
    base_url: str = ""
    username: str = ""
    password: str = ""
    owntracks_user: str = ""
    owntracks_device: str = ""


class RemindersConfig(BaseModel):
    api_tokens: Annotated[list[str], NoDecode] = []
    nominatim_url: str = ""

    @field_validator("api_tokens", mode="before")
    @classmethod
    def _split_tokens(cls, v):
        return _split_csv(v)


class RadicaleConfig(BaseModel):
    """CardDAV storage backend, formerly used for Contacts. No longer read by any
    registered tool — Reminders moved off Radicale onto RemindersServerConfig, and
    Contacts has since moved onto ContactsServerConfig below (see
    gateway/reminders/store.py and gateway/contacts_server/store.py). Kept only for
    the historical one-shot migration scripts under scripts/ that still speak
    CardDAV directly; safe to delete once those are retired."""
    base_url: str = ""
    username: str = ""
    password: str = ""
    contacts_path: str = ""


class RemindersServerConfig(BaseModel):
    """apple-reminders-server on Malcolm — real Apple Reminders via EventKit,
    replacing Radicale as the reminders backend."""
    base_url: str = ""
    bearer_token: str = ""


class ContactsServerConfig(BaseModel):
    """apple-contacts-server on Malcolm — real macOS Contacts via the Contacts
    framework, replacing Radicale as the contacts backend."""
    base_url: str = ""
    bearer_token: str = ""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4000
    # Each entry is `label:secret` or a bare secret (see gateway.auth.parse_clients).
    auth_tokens: Annotated[list[str], NoDecode] = []

    @field_validator("auth_tokens", mode="before")
    @classmethod
    def _split_tokens(cls, v):
        return _split_csv(v)


class UsageLogConfig(BaseModel):
    """Per-request `/mcp` usage logging. Always writes to stdout (lines prefixed
    `usage `); also appends pure JSONL to `path` when set, rotating it."""
    enabled: bool = True
    path: str = ""
    max_bytes: int = 10_485_760
    backups: int = 5


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    mail_archive_server: MailArchiveServerConfig = MailArchiveServerConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    github: GitHubConfig = GitHubConfig()
    calendar_server: CalendarServerConfig = CalendarServerConfig()
    karakeep: KarakeepConfig = KarakeepConfig()
    ebay: EbayConfig = EbayConfig()
    owntracks: OwnTracksConfig = OwnTracksConfig()
    reminders: RemindersConfig = RemindersConfig()
    radicale: RadicaleConfig = RadicaleConfig()
    reminders_server: RemindersServerConfig = RemindersServerConfig()
    contacts_server: ContactsServerConfig = ContactsServerConfig()
    server: ServerConfig = ServerConfig()
    usage_log: UsageLogConfig = UsageLogConfig()
