"""Massive (formerly Polygon.io) adapter.

Free-tier aware: a sliding-window rate limiter enforces POLYGON_RPM, 429s are
retried with backoff, and a one-time capability probe detects what the key's
tier can serve (intraday snapshots and options need paid plans; aggregates and
news work on the free tier). Ingestion consults `capabilities()` and fills
unsupported feeds from the sample generator.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from app.config import get_settings
from app.providers.base import (
    Bar,
    Capabilities,
    CatalystInfo,
    MarketDataProvider,
    OptionsInfo,
    Quote,
)

log = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window limiter: at most `rpm` acquisitions per 60s."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] > 60:
                    self._stamps.popleft()
                if len(self._stamps) < self.rpm:
                    self._stamps.append(now)
                    return
                await asyncio.sleep(60 - (now - self._stamps[0]) + 0.05)


class PolygonProvider(MarketDataProvider):
    name = "polygon"

    def __init__(self) -> None:
        settings = get_settings()
        self._key = settings.polygon_api_key
        self._client = httpx.AsyncClient(
            base_url=settings.polygon_base_url, timeout=30,
            headers={"Authorization": f"Bearer {self._key}"},
        )
        self._limiter = RateLimiter(settings.polygon_rpm)
        self._caps: Capabilities | None = None
        self._grouped_cache: tuple[str, dict[str, dict]] | None = None  # (date, {ticker: row})
        self._grouped_unavailable = False  # some tiers 403 the grouped endpoint entirely

    async def _get(self, path: str, **params) -> dict | None:
        for attempt in range(4):
            await self._limiter.acquire()
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                log.warning("polygon request failed (%s): %s", path, exc)
                await asyncio.sleep(2**attempt)
                continue
            if resp.status_code == 429:
                await asyncio.sleep(15 * (attempt + 1))
                continue
            if resp.status_code in (401, 403):
                log.info("polygon: %s not authorized for this key tier", path)
                return None
            if resp.status_code >= 400:
                log.warning("polygon %s -> %s %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        return None

    async def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps
        notes = []
        today = datetime.now(timezone.utc).date()
        hist = await self._get(
            f"/v2/aggs/ticker/AAPL/range/1/day/{today - timedelta(days=10)}/{today}",
            adjusted="true", sort="asc", limit=10,
        )
        history_ok = bool(hist and hist.get("resultsCount"))
        snap = await self._get("/v2/snapshot/locale/us/markets/stocks/tickers", tickers="AAPL")
        quotes_live = snap is not None
        opts = await self._get("/v3/snapshot/options/AAPL", limit=1)
        options_ok = opts is not None
        news = await self._get("/v2/reference/news", ticker="AAPL", limit=1)
        news_ok = news is not None
        if not quotes_live:
            notes.append("key tier is end-of-day: quotes come from latest daily close")
        if not options_ok:
            notes.append("options flow not in key tier — synthesized from sample generator")
        self._caps = Capabilities(
            history=history_ok, quotes=True, eod_only=not quotes_live,
            options=options_ok, catalysts=news_ok, notes=notes,
        )
        log.info("polygon capabilities: %s", self._caps)
        return self._caps

    async def fetch_daily_history(self, tickers: list[str], days: int) -> dict[str, list[Bar]]:
        """One request per ticker returns the full daily range — the cheapest way
        to backfill on a low-RPM key. Callers batch tickers per cycle."""
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=int(days * 1.6) + 10)
        out: dict[str, list[Bar]] = {}
        for ticker in tickers:
            data = await self._get(
                f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{today}",
                adjusted="true", sort="asc", limit=50000,
            )
            if not data or not data.get("results"):
                continue
            out[ticker] = [
                Bar(ts=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                    open=r["o"], high=r["h"], low=r["l"], close=r["c"],
                    volume=r.get("v", 0), vwap=r.get("vw"))
                for r in data["results"]
            ]
        return out

    async def _grouped_daily(self) -> dict[str, dict]:
        """Latest whole-market EOD bars in a single request. Some tiers 403 this
        endpoint — remember that and stop probing (quotes then fall back to the
        latest stored candle close, which ingestion keeps fresh)."""
        if self._grouped_unavailable:
            return self._grouped_cache[1] if self._grouped_cache else {}
        probe = pd.Timestamp(datetime.now(timezone.utc).date())
        denied = attempted = 0
        for _ in range(6):
            if probe.dayofweek < 5:
                date_str = probe.strftime("%Y-%m-%d")
                if self._grouped_cache and self._grouped_cache[0] == date_str:
                    return self._grouped_cache[1]
                attempted += 1
                data = await self._get(
                    f"/v2/aggs/grouped/locale/us/market/stocks/{date_str}", adjusted="true"
                )
                if data is None:
                    # Free tiers 403 the current (unsettled) session — keep
                    # walking back to the last settled trading day.
                    denied += 1
                elif data.get("resultsCount"):
                    rows = {r["T"]: r for r in data["results"]}
                    self._grouped_cache = (date_str, rows)
                    return rows
            probe -= pd.Timedelta(days=1)
        if attempted and denied == attempted:
            self._grouped_unavailable = True  # endpoint truly not in this tier
            log.info("polygon: grouped-daily not in key tier; using stored closes")
        return self._grouped_cache[1] if self._grouped_cache else {}

    async def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        caps = await self.capabilities()
        if not caps.eod_only:
            data = await self._get(
                "/v2/snapshot/locale/us/markets/stocks/tickers", tickers=",".join(tickers)
            )
            if data and data.get("tickers"):
                quotes = []
                for t in data["tickers"]:
                    day, prev, last = t.get("day", {}), t.get("prevDay", {}), t.get("lastTrade", {})
                    q = t.get("lastQuote", {})
                    price = last.get("p") or day.get("c") or prev.get("c")
                    if not price:
                        continue
                    quotes.append(Quote(
                        ticker=t["ticker"], price=price,
                        bid=q.get("p"), ask=q.get("P"),
                        prev_close=prev.get("c"), day_volume=day.get("v"),
                    ))
                return quotes
        rows = await self._grouped_daily()
        return [
            Quote(ticker=t, price=rows[t]["c"], day_volume=rows[t].get("v"))
            for t in tickers if t in rows
        ]

    async def fetch_options(self, tickers: list[str]) -> list[OptionsInfo]:
        caps = await self.capabilities()
        if not caps.options:
            return []
        out = []
        for ticker in tickers:
            data = await self._get(f"/v3/snapshot/options/{ticker}", limit=250)
            if not data or not data.get("results"):
                continue
            call_vol = put_vol = 0.0
            ivs = []
            for c in data["results"]:
                vol = (c.get("day") or {}).get("volume") or 0
                if (c.get("details") or {}).get("contract_type") == "call":
                    call_vol += vol
                else:
                    put_vol += vol
                if c.get("implied_volatility"):
                    ivs.append(c["implied_volatility"])
            pcr = put_vol / call_vol if call_vol else None
            out.append(OptionsInfo(
                ticker=ticker, call_volume=call_vol, put_volume=put_vol,
                put_call_ratio=round(pcr, 2) if pcr else None,
                iv=round(sum(ivs) / len(ivs), 3) if ivs else None,
            ))
        return out

    async def fetch_catalysts(self, tickers: list[str]) -> list[CatalystInfo]:
        caps = await self.capabilities()
        if not caps.catalysts:
            return []
        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        out = []
        for ticker in tickers:
            data = await self._get("/v2/reference/news", ticker=ticker, limit=5,
                                   **{"published_utc.gte": since})
            for item in (data or {}).get("results", []):
                sentiment = None
                for ins in item.get("insights") or []:
                    if ins.get("ticker") == ticker:
                        sentiment = {"positive": 0.6, "neutral": 0.0, "negative": -0.6}.get(
                            ins.get("sentiment"))
                pub = item.get("published_utc")
                out.append(CatalystInfo(
                    ticker=ticker, kind="news", headline=item.get("title", "")[:300],
                    sentiment=sentiment,
                    event_date=datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None,
                ))
        return out

    async def close(self) -> None:
        await self._client.aclose()
