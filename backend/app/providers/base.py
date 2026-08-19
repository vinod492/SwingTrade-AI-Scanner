"""Provider abstractions. Every data source (sample, Massive/Polygon, Alpaca)
implements the same interface, so switching is a config change only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


@dataclass(slots=True)
class Quote:
    ticker: str
    price: float
    bid: float | None = None
    ask: float | None = None
    prev_close: float | None = None
    day_volume: float | None = None


@dataclass(slots=True)
class OptionsInfo:
    ticker: str
    call_volume: float | None = None
    put_volume: float | None = None
    put_call_ratio: float | None = None
    avg_call_volume: float | None = None
    oi_change_pct: float | None = None
    iv: float | None = None
    iv_change: float | None = None
    unusual: bool = False


@dataclass(slots=True)
class CatalystInfo:
    ticker: str
    kind: str  # earnings | upgrade | news | trial_readout | fda_decision
    headline: str = ""
    sentiment: float | None = None  # -1 .. 1
    event_date: datetime | None = None
    # True only when `event_date` is confirmed by a real calendar source
    # (e.g. Finnhub earnings calendar). False = deterministic sample
    # placeholder — always label it as projected, never present it as fact.
    verified: bool = False


@dataclass(slots=True)
class ShortInterestInfo:
    ticker: str
    short_pct_float: float | None = None  # 0-100
    days_to_cover: float | None = None


@dataclass(slots=True)
class Capabilities:
    """What the active provider/key tier can actually serve. Ingestion consults
    this and backfills anything unsupported from the sample generator."""

    history: bool = True
    quotes: bool = True          # real-time or delayed intraday quotes
    eod_only: bool = False       # quotes are end-of-day closes (e.g. Massive free tier)
    options: bool = False
    catalysts: bool = False
    notes: list[str] = field(default_factory=list)


class MarketDataProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def capabilities(self) -> Capabilities: ...

    @abstractmethod
    async def fetch_daily_history(self, tickers: list[str], days: int) -> dict[str, list[Bar]]:
        """Daily OHLCV history per ticker, oldest first."""

    @abstractmethod
    async def fetch_quotes(self, tickers: list[str]) -> list[Quote]: ...

    async def fetch_options(self, tickers: list[str]) -> list[OptionsInfo]:
        return []

    async def fetch_catalysts(self, tickers: list[str]) -> list[CatalystInfo]:
        return []

    async def fetch_short_interest(self, tickers: list[str]) -> list[ShortInterestInfo]:
        return []

    async def close(self) -> None:
        return None


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def analyze(self, context: dict) -> dict:
        """Return {'why_moving', 'bull_case', 'bear_case', 'technical', 'trade_plan',
        'risk_factors'} for the ticker context assembled by services.ai_analysis."""


def get_market_provider() -> MarketDataProvider:
    from app.config import get_settings

    settings = get_settings()
    if settings.data_provider == "polygon":
        from app.providers.polygon import PolygonProvider

        return PolygonProvider()
    if settings.data_provider == "alpaca":
        from app.providers.alpaca import AlpacaProvider

        return AlpacaProvider()
    from app.providers.sample import SampleProvider

    return SampleProvider()


def get_ai_provider() -> AIProvider:
    from app.config import get_settings

    settings = get_settings()
    if settings.ai_provider == "openai" and settings.openai_api_key:
        from app.providers.openai_ai import OpenAIProvider

        return OpenAIProvider()
    from app.providers.sample_ai import SampleAIProvider

    return SampleAIProvider()
