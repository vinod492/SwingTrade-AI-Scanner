"""Market data ingestion: history backfill, quote/options/catalyst refresh.

Provider-agnostic: consults the active provider's capabilities and fills any
feed it can't serve (options flow, catalysts, intraday quotes on EOD tiers)
from the deterministic sample generator so the pipeline is never starved.
Designed to scale to thousands of tickers: work is budgeted per cycle and all
writes are batched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Candle, Catalyst, OptionsActivity, ShortInterest, Snapshot, Symbol
from app.providers.base import (
    Capabilities,
    CatalystInfo,
    MarketDataProvider,
    OptionsInfo,
    Quote,
    ShortInterestInfo,
)

log = logging.getLogger(__name__)

MIN_HISTORY_BARS = 60  # bars required before a symbol is scored


async def load_universe(session: AsyncSession) -> list[Symbol]:
    settings = get_settings()
    return list((await session.execute(
        select(Symbol).where(Symbol.active == True)  # noqa: E712
        .order_by(Symbol.id).limit(settings.universe_limit)
    )).scalars())


async def history_status(session: AsyncSession) -> dict[int, tuple[int, datetime | None]]:
    """{symbol_id: (bar_count, latest_ts)} for daily candles."""
    rows = (await session.execute(
        select(Candle.symbol_id, func.count(Candle.id), func.max(Candle.ts))
        .where(Candle.timeframe == "1d").group_by(Candle.symbol_id)
    )).all()
    return {sid: (count, latest) for sid, count, latest in rows}


def _as_utc(ts: datetime | None) -> datetime | None:
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


async def backfill_history(
    session: AsyncSession,
    provider: MarketDataProvider,
    symbols: list[Symbol],
    budget: int,
) -> int:
    """Fetch full daily history for up to `budget` symbols that are missing or
    stale, replacing their stored 1d candles. Returns symbols updated."""
    settings = get_settings()
    status = await history_status(session)
    today = datetime.now(timezone.utc).date()

    def needs(sym: Symbol) -> bool:
        count, latest = status.get(sym.id, (0, None))
        latest = _as_utc(latest)
        if count < MIN_HISTORY_BARS or latest is None:
            return True
        # EOD data always lags by one trading day, so comparing against a
        # fixed wall-clock window (e.g. 20h) would mark it "stale" forever —
        # a candle dated yesterday is never within 20h of "now" this
        # afternoon. Compare calendar-day gap instead: a 1-day-old bar is
        # the freshest obtainable and shouldn't be re-fetched every cycle.
        return (today - latest.date()).days > 1

    candidates = sorted(
        (s for s in symbols if needs(s)),
        key=lambda s: status.get(s.id, (0, None))[0],  # never-loaded first
    )[:budget]
    if not candidates:
        return 0

    by_ticker = {s.ticker: s for s in candidates}
    history = await provider.fetch_daily_history(list(by_ticker), settings.history_days)
    for ticker, bars in history.items():
        if not bars:
            continue
        sym = by_ticker[ticker]
        await session.execute(delete(Candle).where(
            Candle.symbol_id == sym.id, Candle.timeframe == "1d",
            Candle.ts >= bars[0].ts,
        ))
        session.add_all([
            Candle(symbol_id=sym.id, timeframe="1d", ts=b.ts, open=b.open, high=b.high,
                   low=b.low, close=b.close, volume=b.volume, vwap=b.vwap)
            for b in bars
        ])
    await session.commit()
    log.info("backfilled daily history for %d symbols", len(history))
    return len(history)


async def refresh_quotes(
    session: AsyncSession,
    provider: MarketDataProvider,
    symbols: list[Symbol],
    caps: Capabilities,
) -> dict[str, Quote]:
    """Fetch latest quotes, upsert snapshots, return quotes by ticker."""
    tickers = [s.ticker for s in symbols]
    quotes = {q.ticker: q for q in await provider.fetch_quotes(tickers)}
    id_by_ticker = {s.ticker: s.id for s in symbols}

    # EOD tiers may serve no quote endpoint at all — synthesize quotes from the
    # freshest stored candles so snapshots/watchlist P&L stay populated.
    missing = [s for s in symbols if s.ticker not in quotes]
    if missing:
        closes = await _last_two_closes(session, [s.id for s in missing])
        for sym in missing:
            pair = closes.get(sym.id)
            if pair:
                quotes[sym.ticker] = Quote(ticker=sym.ticker, price=pair[0],
                                           prev_close=pair[1])
    if not quotes:
        return {}
    existing = {s.symbol_id: s for s in (await session.execute(
        select(Snapshot).where(Snapshot.symbol_id.in_(id_by_ticker.values()))
    )).scalars()}

    # On EOD tiers prev_close is missing — derive it from the stored candle
    # before the latest one so day-change is still meaningful.
    need_prev = [t for t, q in quotes.items() if q.prev_close is None and t in id_by_ticker]
    if need_prev:
        prev_map = await _prev_closes(session, [id_by_ticker[t] for t in need_prev])
        for t in need_prev:
            quotes[t].prev_close = prev_map.get(id_by_ticker[t])

    now = datetime.now(timezone.utc)
    for ticker, q in quotes.items():
        sid = id_by_ticker.get(ticker)
        if sid is None:
            continue
        change = None
        if q.prev_close and q.prev_close > 0 and q.price != q.prev_close:
            change = (q.price - q.prev_close) / q.prev_close * 100
        elif q.prev_close:
            change = 0.0
        spread = None
        if q.bid and q.ask and q.price:
            spread = (q.ask - q.bid) / q.price * 100
        snap = existing.get(sid)
        if snap is None:
            snap = Snapshot(symbol_id=sid)
            session.add(snap)
        snap.price = q.price
        snap.bid, snap.ask, snap.spread_pct = q.bid, q.ask, spread
        snap.prev_close, snap.day_change_pct = q.prev_close, change
        snap.day_volume = q.day_volume
        snap.updated_at = now
    await session.commit()
    return quotes


async def _last_two_closes(
    session: AsyncSession, symbol_ids: list[int]
) -> dict[int, tuple[float, float | None]]:
    """(latest close, previous close) per symbol from stored daily candles."""
    rows = (await session.execute(
        select(Candle.symbol_id, Candle.ts, Candle.close)
        .where(Candle.symbol_id.in_(symbol_ids), Candle.timeframe == "1d")
        .order_by(Candle.symbol_id, Candle.ts.desc())
    )).all()
    seen: dict[int, int] = {}
    out: dict[int, tuple[float, float | None]] = {}
    for sid, _ts, close in rows:
        seen[sid] = seen.get(sid, 0) + 1
        if seen[sid] == 1:
            out[sid] = (close, None)
        elif seen[sid] == 2:
            out[sid] = (out[sid][0], close)
    return out


async def _prev_closes(session: AsyncSession, symbol_ids: list[int]) -> dict[int, float]:
    """Close of the second-most-recent daily bar per symbol."""
    pairs = await _last_two_closes(session, symbol_ids)
    return {sid: prev for sid, (_last, prev) in pairs.items() if prev is not None}


async def refresh_options(
    session: AsyncSession,
    provider: MarketDataProvider,
    sample: MarketDataProvider,
    symbols: list[Symbol],
    caps: Capabilities,
    priority_tickers: list[str],
) -> dict[str, OptionsInfo]:
    """Options flow — live for priority tickers when the tier allows it,
    synthesized for the rest so the options score component always has input."""
    if caps.options:
        live = {o.ticker: o for o in await provider.fetch_options(priority_tickers[:25])}
    else:
        live = {}
    rest = [s.ticker for s in symbols if s.ticker not in live]
    synth = {o.ticker: o for o in await sample.fetch_options(rest)}
    merged = {**synth, **live}

    id_by_ticker = {s.ticker: s.id for s in symbols}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    await session.execute(delete(OptionsActivity).where(OptionsActivity.ts == today))
    session.add_all([
        OptionsActivity(
            symbol_id=id_by_ticker[t], ts=today, call_volume=o.call_volume,
            put_volume=o.put_volume, put_call_ratio=o.put_call_ratio,
            avg_call_volume=o.avg_call_volume, oi_change_pct=o.oi_change_pct,
            unusual=o.unusual, iv=o.iv, iv_change=o.iv_change,
        )
        for t, o in merged.items() if t in id_by_ticker
    ])
    await session.commit()
    return merged


async def refresh_catalysts(
    session: AsyncSession,
    provider: MarketDataProvider,
    sample: MarketDataProvider,
    symbols: list[Symbol],
    caps: Capabilities,
    priority_tickers: list[str],
) -> dict[str, list[CatalystInfo]]:
    """Catalysts refresh at most once per day (news calls are budget-hungry)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    already = (await session.execute(
        select(func.count(Catalyst.id)).where(Catalyst.created_at >= today_start)
    )).scalar()
    if not already:
        from app.providers.finnhub import fetch_earnings_calendar

        tickers = [s.ticker for s in symbols]
        cats: list[CatalystInfo] = []
        if caps.catalysts:
            cats.extend(await provider.fetch_catalysts(priority_tickers[:10]))
            covered = {c.ticker for c in cats}
            cats.extend(await sample.fetch_catalysts([t for t in tickers if t not in covered]))
        else:
            cats.extend(await sample.fetch_catalysts(tickers))

        # Real earnings dates, independent of DATA_PROVIDER: a successful
        # Finnhub call covers every ticker in the lookahead window, so it's
        # authoritative even for tickers absent from the response (that
        # means "nothing real due soon", not "unknown") — drop every
        # sample-projected "earnings" entry and replace with the real ones.
        # Every other catalyst kind (news/upgrade/trial/FDA) is untouched.
        # Only fall back to the sample projection when the call itself
        # failed (no key / request error), per fetch_earnings_calendar's ok flag.
        real_earnings, real_ok = await fetch_earnings_calendar(set(tickers))
        if real_ok:
            cats = [c for c in cats if c.kind != "earnings"]
            cats.extend(real_earnings)

        id_by_ticker = {s.ticker: s.id for s in symbols}
        await session.execute(delete(Catalyst).where(Catalyst.created_at >= today_start))
        session.add_all([
            Catalyst(symbol_id=id_by_ticker[c.ticker], kind=c.kind, headline=c.headline,
                     sentiment=c.sentiment, event_date=c.event_date, verified=c.verified)
            for c in cats if c.ticker in id_by_ticker
        ])
        await session.commit()

    id_by_ticker = {s.ticker: s.id for s in symbols}
    ticker_by_id = {v: k for k, v in id_by_ticker.items()}
    out: dict[str, list[CatalystInfo]] = {}
    for cat in (await session.execute(
        select(Catalyst).where(Catalyst.created_at >= today_start)
    )).scalars():
        ticker = ticker_by_id.get(cat.symbol_id)
        if ticker:
            out.setdefault(ticker, []).append(CatalystInfo(
                ticker=ticker, kind=cat.kind, headline=cat.headline,
                sentiment=cat.sentiment, event_date=_as_utc(cat.event_date),
                verified=cat.verified,
            ))
    return out


async def refresh_short_interest(
    session: AsyncSession,
    provider: MarketDataProvider,
    sample: MarketDataProvider,
    symbols: list[Symbol],
) -> dict[str, ShortInterestInfo]:
    """Short interest — refreshed at most once/day (real short-interest data
    is only reported bi-monthly by FINRA, so there's no reason to hammer it
    every scan cycle). Falls back to the sample generator for any ticker the
    active provider doesn't cover (i.e. almost always, on free tiers)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    id_by_ticker = {s.ticker: s.id for s in symbols}

    fresh_ids = {r for r, in (await session.execute(
        select(ShortInterest.symbol_id).where(
            ShortInterest.symbol_id.in_(id_by_ticker.values()),
            ShortInterest.updated_at >= today_start,
        )
    )).all()}
    stale = [s for s in symbols if s.id not in fresh_ids]
    if stale:
        live = {i.ticker: i for i in await provider.fetch_short_interest([s.ticker for s in stale])}
        rest = [s.ticker for s in stale if s.ticker not in live]
        synth = {i.ticker: i for i in await sample.fetch_short_interest(rest)}
        merged = {**synth, **live}

        now = datetime.now(timezone.utc)
        existing = {r.symbol_id: r for r in (await session.execute(
            select(ShortInterest).where(ShortInterest.symbol_id.in_(id_by_ticker.values()))
        )).scalars()}
        for ticker, info in merged.items():
            sid = id_by_ticker.get(ticker)
            if sid is None:
                continue
            row = existing.get(sid)
            if row is None:
                row = ShortInterest(symbol_id=sid)
                session.add(row)
            row.short_pct_float = info.short_pct_float
            row.days_to_cover = info.days_to_cover
            row.updated_at = now
        await session.commit()

    ticker_by_id = {v: k for k, v in id_by_ticker.items()}
    out: dict[str, ShortInterestInfo] = {}
    for row in (await session.execute(
        select(ShortInterest).where(ShortInterest.symbol_id.in_(id_by_ticker.values()))
    )).scalars():
        ticker = ticker_by_id.get(row.symbol_id)
        if ticker:
            out[ticker] = ShortInterestInfo(
                ticker=ticker, short_pct_float=row.short_pct_float,
                days_to_cover=row.days_to_cover,
            )
    return out
