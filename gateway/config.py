from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class VikunjaConfig(BaseModel):
    base_url: str = ""
    api_token: str = ""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4000


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
    vikunja: VikunjaConfig = VikunjaConfig()
    server: ServerConfig = ServerConfig()
