"""Alpaca Market Data adapter. The free plan (IEX feed) supports multi-symbol
bars, snapshots and quotes in single requests, which makes it the best free
choice for near-real-time scanning."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.providers.base import Bar, Capabilities, MarketDataProvider, Quote

log = logging.getLogger(__name__)

_CHUNK = 100  # symbols per request


class AlpacaProvider(MarketDataProvider):
    name = "alpaca"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=settings.alpaca_data_url,
            headers={
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            },
            timeout=30,
        )
        self._feed = "iex"  # free plan; sip requires a paid subscription

    async def _get(self, path: str, **params) -> dict | None:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            log.warning("alpaca request failed (%s): %s", path, exc)
            return None
        if resp.status_code >= 400:
            log.warning("alpaca %s -> %s %s", path, resp.status_code, resp.text[:200])
            return None
        return resp.json()

    async def capabilities(self) -> Capabilities:
        return Capabilities(
            history=True, quotes=True, options=False, catalysts=False,
            notes=["IEX feed", "options/catalysts synthesized from sample generator"],
        )

    async def fetch_daily_history(self, tickers: list[str], days: int) -> dict[str, list[Bar]]:
        start = (datetime.now(timezone.utc) - timedelta(days=int(days * 1.6) + 10)).strftime(
            "%Y-%m-%d")
        out: dict[str, list[Bar]] = {}
        for i in range(0, len(tickers), _CHUNK):
            chunk = tickers[i : i + _CHUNK]
            page_token = None
            while True:
                params = {"symbols": ",".join(chunk), "timeframe": "1Day", "start": start,
                          "limit": 10000, "feed": self._feed, "adjustment": "split"}
                if page_token:
                    params["page_token"] = page_token
                data = await self._get("/v2/stocks/bars", **params)
                if not data:
                    break
                for sym, bars in (data.get("bars") or {}).items():
                    out.setdefault(sym, []).extend(
                        Bar(ts=datetime.fromisoformat(b["t"].replace("Z", "+00:00")),
                            open=b["o"], high=b["h"], low=b["l"], close=b["c"],
                            volume=b.get("v", 0), vwap=b.get("vw"))
                        for b in bars
                    )
                page_token = data.get("next_page_token")
                if not page_token:
                    break
        return out

    async def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        quotes: list[Quote] = []
        for i in range(0, len(tickers), _CHUNK):
            chunk = tickers[i : i + _CHUNK]
            data = await self._get("/v2/stocks/snapshots", symbols=",".join(chunk),
                                   feed=self._feed)
            if not data:
                continue
            snapshots = data.get("snapshots", data)  # older API returns flat map
            for sym, snap in snapshots.items():
                if not isinstance(snap, dict):
                    continue
                trade = snap.get("latestTrade") or {}
                quote = snap.get("latestQuote") or {}
                daily = snap.get("dailyBar") or {}
                prev = snap.get("prevDailyBar") or {}
                price = trade.get("p") or daily.get("c")
                if not price:
                    continue
                quotes.append(Quote(
                    ticker=sym, price=price, bid=quote.get("bp"), ask=quote.get("ap"),
                    prev_close=prev.get("c"), day_volume=daily.get("v"),
                ))
        return quotes

    async def close(self) -> None:
        await self._client.aclose()
