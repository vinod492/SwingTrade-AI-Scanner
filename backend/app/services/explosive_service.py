"""Catalyst Radar rows: served from the Redis cache written by the worker,
with a database fallback so the API works even if Redis or the worker is
down (mirrors scanner_service.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExplosiveSignal, IndicatorValue, ShortInterest, Symbol
from app.services.cache import cache_get_json
from app.workers.explosive_job import EXPLOSIVE_KEY


async def get_explosive_rows(session: AsyncSession) -> list[dict]:
    cached = await cache_get_json(EXPLOSIVE_KEY)
    if cached:
        return cached
    return await _rows_from_db(session)


async def _rows_from_db(session: AsyncSession) -> list[dict]:
    signals: dict[int, ExplosiveSignal] = {}
    for sig in (await session.execute(
        select(ExplosiveSignal).order_by(ExplosiveSignal.symbol_id, ExplosiveSignal.ts.desc())
    )).scalars():
        signals.setdefault(sig.symbol_id, sig)
    if not signals:
        return []

    symbols = {s.id: s for s in (await session.execute(
        select(Symbol).where(Symbol.id.in_(signals))
    )).scalars()}
    short_interest = {r.symbol_id: r for r in (await session.execute(
        select(ShortInterest).where(ShortInterest.symbol_id.in_(signals))
    )).scalars()}
    indicators: dict[int, IndicatorValue] = {}
    for ind in (await session.execute(
        select(IndicatorValue).where(IndicatorValue.symbol_id.in_(signals))
        .order_by(IndicatorValue.symbol_id, IndicatorValue.ts.desc())
    )).scalars():
        indicators.setdefault(ind.symbol_id, ind)

    now = datetime.now(timezone.utc)
    rows = []
    for sid, sig in signals.items():
        sym = symbols.get(sid)
        if sym is None:
            continue
        si = short_interest.get(sid)
        ind = indicators.get(sid)
        catalyst_date = sig.catalyst_date
        if catalyst_date is not None and catalyst_date.tzinfo is None:
            catalyst_date = catalyst_date.replace(tzinfo=timezone.utc)
        rows.append({
            "symbol_id": sid, "ticker": sym.ticker, "name": sym.name, "sector": sym.sector,
            "explosive_score": sig.explosive_score,
            "catalyst_pts": sig.catalyst_pts, "squeeze_pts": sig.squeeze_pts,
            "float_pts": sig.float_pts, "iv_pts": sig.iv_pts, "volume_pts": sig.volume_pts,
            "catalyst_kind": sig.catalyst_kind, "catalyst_headline": sig.catalyst_headline,
            "catalyst_date": catalyst_date.isoformat() if catalyst_date else None,
            "catalyst_verified": sig.catalyst_verified,
            "days_to_catalyst": max(0, (catalyst_date - now).days) if catalyst_date else None,
            "short_pct_float": si.short_pct_float if si else None,
            "days_to_cover": si.days_to_cover if si else None,
            "iv_rank": None,
            "float_shares": sym.float_shares,
            "rel_volume": ind.rel_volume if ind else None,
            "reasons": sig.reasons or [],
        })
    rows.sort(key=lambda r: r["explosive_score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows
