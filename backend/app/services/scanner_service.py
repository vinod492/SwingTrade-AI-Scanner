"""Scanner rows: served from the Redis cache written by the worker, with a
database fallback so the API works even if Redis (or the worker) is down."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Score, Snapshot, Symbol, IndicatorValue, OptionsActivity
from app.services.cache import SCANNER_KEY, cache_get_json


async def get_scanner_rows(session: AsyncSession) -> list[dict]:
    cached = await cache_get_json(SCANNER_KEY)
    if cached:
        return cached
    return await _rows_from_db(session)


async def _rows_from_db(session: AsyncSession) -> list[dict]:
    """Rebuild scanner rows from the latest persisted Score per symbol."""
    scores: dict[int, Score] = {}
    for score in (await session.execute(
        select(Score).order_by(Score.symbol_id, Score.ts.desc())
    )).scalars():
        scores.setdefault(score.symbol_id, score)  # first seen = latest per symbol

    if not scores:
        return []

    symbols = {s.id: s for s in (await session.execute(
        select(Symbol).where(Symbol.id.in_(scores))
    )).scalars()}
    snapshots = {s.symbol_id: s for s in (await session.execute(
        select(Snapshot).where(Snapshot.symbol_id.in_(scores))
    )).scalars()}
    indicators: dict[int, IndicatorValue] = {}
    for ind in (await session.execute(
        select(IndicatorValue).where(IndicatorValue.symbol_id.in_(scores))
        .order_by(IndicatorValue.symbol_id, IndicatorValue.ts.desc())
    )).scalars():
        indicators.setdefault(ind.symbol_id, ind)
    options: dict[int, OptionsActivity] = {}
    for opt in (await session.execute(
        select(OptionsActivity).where(OptionsActivity.symbol_id.in_(scores))
        .order_by(OptionsActivity.symbol_id, OptionsActivity.ts.desc())
    )).scalars():
        options.setdefault(opt.symbol_id, opt)

    rows = []
    for sid, score in scores.items():
        sym = symbols.get(sid)
        if sym is None:
            continue
        snap = snapshots.get(sid)
        ind = indicators.get(sid)
        opt = options.get(sid)
        rows.append({
            "symbol_id": sid,
            "ticker": sym.ticker,
            "name": sym.name,
            "sector": sym.sector,
            "price": snap.price if snap else None,
            "day_change_pct": snap.day_change_pct if snap else None,
            "volume": snap.day_volume if snap else None,
            "rel_volume": ind.rel_volume if ind else None,
            "atr_pct": ind.atr_pct if ind else None,
            "rsi": ind.rsi if ind else None,
            "trend": score.trend,
            "swing_score": score.swing_score,
            "momentum_pts": score.momentum_pts, "volatility_pts": score.volatility_pts,
            "volume_pts": score.volume_pts, "breakout_pts": score.breakout_pts,
            "options_pts": score.options_pts, "catalyst_pts": score.catalyst_pts,
            "setup_label": score.setup_label,
            "reasons": [],
            "entry": score.entry, "entry_high": score.entry_high, "stop": score.stop,
            "target": score.target, "risk_pct": score.risk_pct,
            "reward_pct": score.reward_pct, "rr_ratio": score.rr_ratio,
            "support": ind.support if ind else None,
            "resistance": ind.resistance if ind else None,
            "unusual_options": bool(opt.unusual) if opt else False,
            "updated_at": (snap.updated_at.isoformat() if snap and snap.updated_at else None),
        })
    rows = [r for r in rows if r["price"] is not None]
    rows.sort(key=lambda r: r["swing_score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def apply_filters(
    rows: list[dict],
    min_score: float | None = None,
    sector: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_rel_volume: float | None = None,
    trend: str | None = None,
    search: str | None = None,
) -> list[dict]:
    def keep(r: dict) -> bool:
        if min_score is not None and r["swing_score"] < min_score:
            return False
        if sector and r["sector"] != sector:
            return False
        if min_price is not None and (r["price"] or 0) < min_price:
            return False
        if max_price is not None and (r["price"] or 0) > max_price:
            return False
        if min_rel_volume is not None and (r["rel_volume"] or 0) < min_rel_volume:
            return False
        if trend and r["trend"] != trend:
            return False
        if search:
            q = search.lower()
            if q not in r["ticker"].lower() and q not in r["name"].lower():
                return False
        return True

    return [r for r in rows if keep(r)]
