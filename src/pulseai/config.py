"""Runtime configuration.

Every setting has a default that works against docker-compose.yml, so a fresh
clone runs without a .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PULSEAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://pulseai:pulseai@localhost:5433/pulseai"
    redis_url: str = "redis://localhost:6380/0"

    user_agent: str = "pulseai/0.1 (+https://github.com/ajaiupadhyaya/slopsentimentmonitor)"
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    #: Multiplier on retry backoff. Tests set this to 0 — otherwise exercising
    #: the retry paths costs minutes of real sleeping.
    http_backoff_factor: float = 1.0

    github_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None

    analyzer: Literal["auto", "local", "heuristic"] = "auto"

    @property
    def sync_database_url(self) -> str:
        """Alembic drives migrations synchronously."""
        return self.database_url.replace("+asyncpg", "+psycopg2").replace(
            "postgresql+psycopg2", "postgresql"
        )

    @property
    def reddit_enabled(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
