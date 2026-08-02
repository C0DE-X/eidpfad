from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./eidpfad.db"
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    protocol_version: int = 2
    log_level: str = "info"
    proxy_headers: bool = False
    forwarded_allow_ips: str = "127.0.0.1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
