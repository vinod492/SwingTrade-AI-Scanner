"""Application configuration loaded from environment / .env.

Checks both the repo-root .env (local dev convention) and a backend-local
.env; real environment variables always win.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Core
    database_url: str = "sqlite+aiosqlite:///./swingtrade.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    encryption_key: str = ""
    access_token_minutes: int = 30
    refresh_token_days: int = 14

    # Market data provider: sample | polygon | alpaca
    data_provider: str = "sample"
    polygon_api_key: str = ""
    polygon_base_url: str = "https://api.polygon.io"
    polygon_rpm: int = 5
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_data_url: str = "https://data.alpaca.markets"

    # AI provider: sample | openai
    ai_provider: str = "sample"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ai_cache_ttl_seconds: int = 3600

    # Real earnings-calendar dates for Catalyst Radar (free tier: finnhub.io).
    # Independent of DATA_PROVIDER. Empty = every earnings date shown is a
    # projected placeholder, honestly labeled as such — never silently real.
    finnhub_api_key: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Hosts like Render/Railway/Heroku hand out postgres:// URLs; the
        async engine needs the asyncpg dialect spelled out."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Scanner behaviour
    scan_interval_seconds: int = 60
    history_days: int = 504
    universe_limit: int = 500
    top_n_ideas: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
