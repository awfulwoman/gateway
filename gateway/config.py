from typing import Annotated
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(v):
    return [t.strip() for t in v.split(",") if t.strip()] if isinstance(v, str) else v


class IMAPConfig(BaseModel):
    host: str = "imap.mailbox.org"
    port: int = 993
    username: str = ""
    password: str = ""


class ObsidianConfig(BaseModel):
    vault_path: str = ""


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
    db_path: str = ""
    api_tokens: Annotated[list[str], NoDecode] = []
    nominatim_url: str = ""

    @field_validator("api_tokens", mode="before")
    @classmethod
    def _split_tokens(cls, v):
        return _split_csv(v)


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4000
    auth_tokens: Annotated[list[str], NoDecode] = []

    @field_validator("auth_tokens", mode="before")
    @classmethod
    def _split_tokens(cls, v):
        return _split_csv(v)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    imap: IMAPConfig = IMAPConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    karakeep: KarakeepConfig = KarakeepConfig()
    owntracks: OwnTracksConfig = OwnTracksConfig()
    reminders: RemindersConfig = RemindersConfig()
    server: ServerConfig = ServerConfig()
