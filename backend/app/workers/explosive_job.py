"""Catalyst Radar pipeline: pending binary catalysts + short interest + IV
positioning + volume build → ExplosiveSignal rows + Redis cache + WS event.

Runs once per scan cycle, after the directional Swing Score pipeline — it
reads the indicator/options data that cycle already refreshed rather than
issuing its own provider calls (only short interest needs its own fetch,
handled separately in ingestion.refresh_short_interest).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExplosiveSignal, IndicatorValue, OptionsActivity, Symbol
from app.providers.base import CatalystInfo, ShortInterestInfo
from app.services.cache import cache_set_json, publish_event
from app.services.explosive import iv_rank_percentile, score_explosive

EXPLOSIVE_KEY = "swingtrade:explosive:latest"
IV_HISTORY_DAYS = 60
MIN_EXPLOSIVE_SCORE = 15  # below this, "elevated move potential" isn't a meaningful claim


async def _iv_histories(session: AsyncSession, symbol_ids: list[int]) -> dict[int, list[float]]:
    rows = (await session.execute(
        select(OptionsActivity.symbol_id, OptionsActivity.iv)
        .where(OptionsActivity.symbol_id.in_(symbol_ids), OptionsActivity.iv.is_not(None))
        .order_by(OptionsActivity.symbol_id, OptionsActivity.ts.desc())
    )).all()
    out: dict[int, list[float]] = {}
    for sid, iv in rows:
        bucket = out.setdefault(sid, [])
        if len(bucket) < IV_HISTORY_DAYS:
            bucket.append(iv)
    return out


async def _rel_volume_trends(session: AsyncSession, symbol_ids: list[int]) -> dict[int, bool]:
    """True if relative volume over the most recent stored days is trending
    up vs. the few days before that — a crude "positioning ahead of the
    date" signal."""
    rows = (await session.execute(
        select(IndicatorValue.symbol_id, IndicatorValue.ts, IndicatorValue.rel_volume)
        .where(IndicatorValue.symbol_id.in_(symbol_ids), IndicatorValue.rel_volume.is_not(None))
        .order_by(IndicatorValue.symbol_id, IndicatorValue.ts.desc())
    )).all()
    by_symbol: dict[int, list[float]] = {}
    for sid, _ts, rv in rows:
        by_symbol.setdefault(sid, []).append(rv)
    out: dict[int, bool] = {}
    for sid, values in by_symbol.items():
        recent, prior = values[:3], values[3:6]
        out[sid] = bool(recent and prior and (sum(recent) / len(recent)) > (sum(prior) / len(prior)) * 1.1)
    return out


async def compute_and_store_explosive(
    session: AsyncSession,
    symbols: list[Symbol],
    catalysts_map: dict[str, list[CatalystInfo]],
    short_interest_map: dict[str, ShortInterestInfo],
) -> list[dict]:
    ids = [s.id for s in symbols]
    iv_hist = await _iv_histories(session, ids)
    vol_trend = await _rel_volume_trends(session, ids)

    latest_options: dict[int, OptionsActivity] = {}
    for opt in (await session.execute(
        select(OptionsActivity).where(OptionsActivity.symbol_id.in_(ids))
        .order_by(OptionsActivity.symbol_id, OptionsActivity.ts.desc())
    )).scalars():
        latest_options.setdefault(opt.symbol_id, opt)
    latest_ind: dict[int, IndicatorValue] = {}
    for ind in (await session.execute(
        select(IndicatorValue).where(IndicatorValue.symbol_id.in_(ids))
        .order_by(IndicatorValue.symbol_id, IndicatorValue.ts.desc())
    )).scalars():
        latest_ind.setdefault(ind.symbol_id, ind)

    now = datetime.now(timezone.utc)
    day_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows: list[dict] = []

    for sym in symbols:
        opt = latest_options.get(sym.id)
        ind = latest_ind.get(sym.id)
        si = short_interest_map.get(sym.ticker)
        iv_rank = iv_rank_percentile(iv_hist.get(sym.id, []), opt.iv if opt else None)

        bd = score_explosive(
            catalysts=catalysts_map.get(sym.ticker, []),
            short_pct_float=si.short_pct_float if si else None,
            days_to_cover=si.days_to_cover if si else None,
            iv_rank=iv_rank,
            iv_rising=bool(opt and opt.iv_change and opt.iv_change > 0),
            float_shares=sym.float_shares,
            rel_volume=ind.rel_volume if ind else None,
            rel_volume_trend_up=vol_trend.get(sym.id, False),
            now=now,
        )
        await session.execute(delete(ExplosiveSignal).where(
            ExplosiveSignal.symbol_id == sym.id, ExplosiveSignal.ts == day_ts))
        if bd.total < MIN_EXPLOSIVE_SCORE:
            continue

        session.add(ExplosiveSignal(
            symbol_id=sym.id, ts=day_ts, explosive_score=bd.total,
            catalyst_pts=bd.catalyst, squeeze_pts=bd.squeeze, float_pts=bd.float_amp,
            iv_pts=bd.iv, volume_pts=bd.volume, catalyst_kind=bd.catalyst_kind,
            catalyst_headline=bd.catalyst_headline, catalyst_date=bd.catalyst_date,
            reasons=bd.reasons,
        ))
        rows.append({
            "symbol_id": sym.id, "ticker": sym.ticker, "name": sym.name, "sector": sym.sector,
            "explosive_score": bd.total,
            "catalyst_pts": bd.catalyst, "squeeze_pts": bd.squeeze, "float_pts": bd.float_amp,
            "iv_pts": bd.iv, "volume_pts": bd.volume,
            "catalyst_kind": bd.catalyst_kind, "catalyst_headline": bd.catalyst_headline,
            "catalyst_date": bd.catalyst_date.isoformat() if bd.catalyst_date else None,
            "days_to_catalyst": bd.days_to_catalyst,
            "short_pct_float": si.short_pct_float if si else None,
            "days_to_cover": si.days_to_cover if si else None,
            "iv_rank": iv_rank,
            "float_shares": sym.float_shares,
            "rel_volume": ind.rel_volume if ind else None,
            "reasons": bd.reasons,
        })

    await session.commit()
    rows.sort(key=lambda r: r["explosive_score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    await cache_set_json(EXPLOSIVE_KEY, rows)
    await publish_event("explosive", {"count": len(rows), "top": rows[:20]})
    return rows
