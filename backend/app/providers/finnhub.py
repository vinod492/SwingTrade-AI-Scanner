"""Finnhub earnings-calendar adapter — the one Catalyst Radar input that's
cheap to make genuinely real. Free tier (60 req/min, no card) includes the
earnings-calendar endpoint, which returns every company reporting in a date
range in a single call (no per-ticker requests needed).

Independent of DATA_PROVIDER: this fills in real earnings dates regardless
of which market-data provider is active, because "when does X report" has
nothing to do with where prices come from. If FINNHUB_API_KEY is unset or
the call fails, callers fall back to the sample generator's clearly-labeled
projection — never silently to a fabricated "real" date.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.providers.base import CatalystInfo

log = logging.getLogger(__name__)

_SESSION_LABELS = {"bmo": "before market open", "amc": "after market close"}


async def fetch_earnings_calendar(
    tickers: set[str], lookahead_days: int = 45
) -> list[CatalystInfo]:
    """Real upcoming earnings dates for any ticker in `tickers` within the
    next `lookahead_days`. Returns [] (never raises) if no key is configured
    or the request fails, so callers can unconditionally fall back."""
    settings = get_settings()
    if not settings.finnhub_api_key:
        return []

    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=lookahead_days)
    try:
        async with httpx.AsyncClient(base_url="https://finnhub.io/api/v1", timeout=20) as client:
            resp = await client.get("/calendar/earnings", params={
                "from": today.isoformat(), "to": horizon.isoformat(),
                "token": settings.finnhub_api_key,
            })
        if resp.status_code != 200:
            log.warning("finnhub earnings calendar -> %s %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("finnhub earnings calendar request failed: %s", exc)
        return []
    except ValueError as exc:  # malformed JSON
        log.warning("finnhub earnings calendar returned unparseable body: %s", exc)
        return []

    out: list[CatalystInfo] = []
    for item in data.get("earningsCalendar", []) or []:
        symbol = item.get("symbol")
        event_date = item.get("date")
        if symbol not in tickers or not event_date:
            continue
        try:
            when = datetime.fromisoformat(event_date).replace(
                hour=12, minute=0, second=0, tzinfo=timezone.utc)
        except ValueError:
            continue
        session = _SESSION_LABELS.get(item.get("hour", ""), "")
        out.append(CatalystInfo(
            ticker=symbol, kind="earnings",
            headline=f"{symbol} reports earnings {event_date}"
                     + (f" ({session})" if session else "") + " — confirmed date",
            event_date=when, verified=True,
        ))
    return out
