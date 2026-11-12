from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLITEIA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://politeia:politeia@localhost:5432/politeia"
    cors_origins: str = "http://localhost:5173"
    http_timeout_s: float = 30.0
    user_agent: str = "Politeia/0.1 (+https://github.com/NauCapitania/Politeia)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
