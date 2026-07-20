"""Deterministic synthetic market data.

Every series is a pure function of (ticker, calendar date), so runs are
reproducible, tests are stable, and the same ticker always tells the same
story. Regimes are assigned per ticker so the scanner always finds a mix of
breakouts, uptrends, bases and downtrends; volume/options/catalyst events are
seeded so alert rules demonstrably fire.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from app.providers.base import (
    Bar,
    Capabilities,
    CatalystInfo,
    MarketDataProvider,
    OptionsInfo,
    Quote,
)
from app.db.universe import UNIVERSE

_FLOAT_BY_TICKER = {t: fl * 1e9 for t, _, _, _, fl in UNIVERSE}

# Regimes: (daily drift, breakout tail in last ~10 days)
_REGIMES = [
    (0.0012, True),   # strong uptrend, fresh breakout
    (0.0008, False),  # steady uptrend
    (0.0000, True),   # long base resolving into breakout attempt
    (0.0000, False),  # choppy / rangebound
    (-0.0009, False), # downtrend
]


def _seed(ticker: str) -> int:
    return zlib.crc32(ticker.encode())


def _regime(ticker: str) -> tuple[float, bool]:
    return _REGIMES[_seed(ticker) % len(_REGIMES)]


def _base_price(ticker: str) -> float:
    return 12.0 + (_seed(ticker) % 4801) / 10.0  # $12 .. $492


def _base_volume(ticker: str) -> float:
    fl = _FLOAT_BY_TICKER.get(ticker, 5e8)
    return max(4e5, fl * 0.004)  # ~0.4% of float turns over daily


def trading_days(end: datetime, days: int) -> pd.DatetimeIndex:
    """Business days ending at the last business day on/before `end` (UTC)."""
    end_date = pd.Timestamp(end.date())
    if end_date.dayofweek >= 5:
        end_date -= pd.offsets.BDay(1)
    return pd.bdate_range(end=end_date, periods=days, tz="UTC")


_CANONICAL_DAYS = 600


@lru_cache(maxsize=2048)
def _full_frame(ticker: str, end_key: str) -> pd.DataFrame:
    """Canonical 600-session frame ending at `end_key` (YYYY-MM-DD). Shorter
    requests slice this tail, so a 2-day pull always matches the long history."""
    end = datetime.strptime(end_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    idx = trading_days(end, _CANONICAL_DAYS)
    n = len(idx)
    rng = np.random.default_rng(_seed(ticker))
    drift, breakout = _regime(ticker)

    vol = 0.012 + (_seed(ticker) % 17) / 1000.0  # 1.2% .. 2.8% daily
    rets = rng.normal(drift, vol, n)
    # A few seeded shock days (gaps) spread through history
    shock_days = rng.choice(n, size=n // 60, replace=False)
    rets[shock_days] += rng.normal(0, 4 * vol, len(shock_days))
    if breakout:
        rets[-10:] += 0.008  # recent push through resistance

    close = _base_price(ticker) * np.exp(np.cumsum(rets))
    prev_close = np.concatenate([[close[0] / (1 + rets[0])], close[:-1]])
    gap = rng.normal(0, vol / 3, n)
    open_ = prev_close * (1 + gap)
    span = np.abs(rng.normal(vol, vol / 2, n)) * close
    high = np.maximum(open_, close) + span * 0.6
    low = np.minimum(open_, close) - span * 0.6

    base_vol = _base_volume(ticker)
    volume = base_vol * np.exp(rng.normal(0, 0.35, n))
    spike_days = rng.choice(n, size=n // 40, replace=False)
    volume[spike_days] *= rng.uniform(2.5, 5.0, len(spike_days))
    volume[-3:] *= 3.0 if breakout else 1.0  # volume-confirmed breakout

    vwap = (high + low + close) / 3.0
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "vwap": vwap},
        index=idx,
    )


def generate_daily_frame(ticker: str, days: int, end: datetime | None = None) -> pd.DataFrame:
    """OHLCV+vwap frame indexed by UTC session date, oldest first."""
    end = end or datetime.now(timezone.utc)
    end_key = trading_days(end, 1)[-1].strftime("%Y-%m-%d")
    return _full_frame(ticker, end_key).tail(min(days, _CANONICAL_DAYS))


def _intraday_state(ticker: str, now: datetime) -> tuple[float, float, float]:
    """(price multiplier vs last close, fraction of session elapsed, relvol factor).

    Evolves minute-by-minute through a synthetic 6.5h session; deterministic
    per (ticker, date, minute).
    """
    day_key = int(now.strftime("%Y%m%d"))
    rng = np.random.default_rng(_seed(ticker) ^ day_key)
    steps = rng.normal(0.0002 if _regime(ticker)[0] > 0 else -0.0001, 0.0011, 390)
    # Seeded "movers of the day": ~1 in 8 tickers gets a big directional day
    if rng.integers(0, 8) == 0:
        steps += rng.choice([-1, 1]) * 0.00012 * np.arange(390) / 390 * 8

    minute = (now.hour * 60 + now.minute) % 390
    frac = max(minute / 390.0, 0.05)
    mult = float(np.exp(np.cumsum(steps))[minute])
    relvol = float(np.clip(rng.lognormal(0, 0.5), 0.3, 6.0))
    return mult, frac, relvol


class SampleProvider(MarketDataProvider):
    name = "sample"

    async def capabilities(self) -> Capabilities:
        return Capabilities(history=True, quotes=True, options=True, catalysts=True,
                            notes=["synthetic sample data"])

    async def fetch_daily_history(self, tickers: list[str], days: int) -> dict[str, list[Bar]]:
        out: dict[str, list[Bar]] = {}
        for ticker in tickers:
            frame = generate_daily_frame(ticker, days)
            out[ticker] = [
                Bar(ts=ts.to_pydatetime(), open=float(r.open), high=float(r.high),
                    low=float(r.low), close=float(r.close), volume=float(r.volume),
                    vwap=float(r.vwap))
                for ts, r in frame.iterrows()
            ]
        return out

    async def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        now = datetime.now(timezone.utc)
        quotes = []
        for ticker in tickers:
            frame = generate_daily_frame(ticker, 2)
            prev_close = float(frame["close"].iloc[-1])
            mult, frac, relvol = _intraday_state(ticker, now)
            price = prev_close * mult
            spread = max(0.01, price * 0.0004)
            quotes.append(
                Quote(ticker=ticker, price=round(price, 2),
                      bid=round(price - spread / 2, 2), ask=round(price + spread / 2, 2),
                      prev_close=round(prev_close, 2),
                      day_volume=float(_base_volume(ticker) * relvol * frac))
            )
        return quotes

    async def fetch_options(self, tickers: list[str]) -> list[OptionsInfo]:
        now = datetime.now(timezone.utc)
        day_key = int(now.strftime("%Y%m%d"))
        out = []
        for ticker in tickers:
            rng = np.random.default_rng((_seed(ticker) ^ day_key) + 7)
            avg_calls = _base_volume(ticker) / 90.0
            call_mult = float(np.clip(rng.lognormal(0, 0.7), 0.2, 8.0))
            call_volume = avg_calls * call_mult
            pcr = float(np.clip(rng.normal(0.85, 0.35), 0.25, 2.2))
            _, breakout = _regime(ticker)
            if breakout:
                call_mult *= 1.6
                call_volume *= 1.6
                pcr *= 0.75
            iv = float(np.clip(rng.normal(0.42, 0.15), 0.15, 1.5))
            out.append(
                OptionsInfo(ticker=ticker, call_volume=call_volume,
                            put_volume=call_volume * pcr, put_call_ratio=round(pcr, 2),
                            avg_call_volume=avg_calls,
                            oi_change_pct=round(float(rng.normal(2 if breakout else 0, 4)), 2),
                            iv=round(iv, 3),
                            iv_change=round(float(rng.normal(0.01 if breakout else 0, 0.03)), 4),
                            unusual=call_mult > 2.5)
            )
        return out

    async def fetch_catalysts(self, tickers: list[str]) -> list[CatalystInfo]:
        now = datetime.now(timezone.utc)
        out = []
        for ticker in tickers:
            seed = _seed(ticker)
            if seed % 7 == 0:
                out.append(CatalystInfo(
                    ticker=ticker, kind="earnings",
                    headline=f"{ticker} reports earnings in {seed % 10 + 1} days",
                    event_date=now + timedelta(days=seed % 10 + 1)))
            if seed % 5 == 1:
                out.append(CatalystInfo(
                    ticker=ticker, kind="upgrade", sentiment=0.6,
                    headline=f"Analyst upgrades {ticker} to Buy, raises price target",
                    event_date=now))
            if seed % 3 == 0:
                sentiment = round(((seed >> 4) % 160 - 60) / 100.0, 2)  # -0.6 .. 0.99
                out.append(CatalystInfo(
                    ticker=ticker, kind="news", sentiment=sentiment,
                    headline=f"{ticker} in focus as sector momentum builds",
                    event_date=now))
        return out
