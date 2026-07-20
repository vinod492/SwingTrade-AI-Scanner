"""Application configuration loaded from environment / .env.

Checks both the repo-root .env (local dev convention) and a backend-local
.env; real environment variables always win.
"""
from functools import lru_cache
from pathlib import Path

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

    # Scanner behaviour
    scan_interval_seconds: int = 60
    history_days: int = 504
    universe_limit: int = 500
    top_n_ideas: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
