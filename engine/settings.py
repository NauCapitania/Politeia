from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLITEIA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://politeia:politeia@localhost:5432/politeia"
    cors_origins: str = "http://localhost:5173"
    http_timeout_s: float = 30.0
    user_agent: str = "Politeia/0.1 (+https://github.com/NauCapitania/Politeia)"

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """Accept plain `postgres://` / `postgresql://` URIs (as Supabase shows them) and use psycopg 3."""
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
