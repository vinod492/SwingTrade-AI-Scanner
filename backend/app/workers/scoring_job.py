"""Scoring pipeline: candles + live quote → indicators → Swing Score → trade
plan → persisted rows + Redis scanner cache + WS event + alert evaluation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candle, IndicatorValue, Score, Symbol
from app.providers.base import CatalystInfo, OptionsInfo, Quote
from app.services.alerts import evaluate_alerts
from app.services.cache import SCANNER_KEY, cache_get_json, cache_set_json, publish_event
from app.services.indicators import latest_snapshot
from app.services.scoring import score_symbol
from app.services.trade_plan import build_trade_plan
from app.workers.ingestion import MIN_HISTORY_BARS

log = logging.getLogger(__name__)

PREV_ROWS_KEY = "swingtrade:scanner:prev"


async def load_daily_frames(session: AsyncSession, symbol_ids: list[int]) -> dict[int, pd.DataFrame]:
    """All daily candles for the given symbols in one query, split per symbol."""
    rows = (await session.execute(
        select(Candle.symbol_id, Candle.ts, Candle.open, Candle.high, Candle.low,
               Candle.close, Candle.volume)
        .where(Candle.symbol_id.in_(symbol_ids), Candle.timeframe == "1d")
        .order_by(Candle.symbol_id, Candle.ts)
    )).all()
    if not rows:
        return {}
    df = pd.DataFrame(rows, columns=["symbol_id", "ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return {
        int(sid): g.drop(columns="symbol_id").set_index("ts")
        for sid, g in df.groupby("symbol_id")
    }


def _with_intraday_bar(df: pd.DataFrame, quote: Quote | None) -> pd.DataFrame:
    """Append today's forming bar from the live quote (skip on EOD data where
    the latest stored candle already is the most recent session)."""
    if quote is None or quote.price is None:
        return df
    last_ts = df.index[-1]
    today = pd.Timestamp(datetime.now(timezone.utc).date(), tz="UTC")
    if last_ts >= today:
        return df  # today's bar already stored (EOD tier after close)
    prev_close = float(df["close"].iloc[-1])
    price = float(quote.price)
    bar = pd.DataFrame(
        {"open": prev_close, "high": max(prev_close, price), "low": min(prev_close, price),
         "close": price, "volume": float(quote.day_volume or 0.0)},
        index=[today],
    )
    return pd.concat([df, bar])


async def compute_and_store_scores(
    session: AsyncSession,
    symbols: list[Symbol],
    quotes: dict[str, Quote],
    options_map: dict[str, OptionsInfo],
    catalysts_map: dict[str, list[CatalystInfo]],
) -> list[dict]:
    frames = await load_daily_frames(session, [s.id for s in symbols])
    now = datetime.now(timezone.utc)
    rows: list[dict] = []

    for sym in symbols:
        df = frames.get(sym.id)
        if df is None or len(df) < MIN_HISTORY_BARS:
            continue
        quote = quotes.get(sym.ticker)
        df = _with_intraday_bar(df, quote)
        price = float(quote.price) if quote else float(df["close"].iloc[-1])

        snap = latest_snapshot(df)
        options = options_map.get(sym.ticker)
        catalysts = catalysts_map.get(sym.ticker, [])
        bd = score_symbol(snap, price, options, catalysts, now=now)
        plan = build_trade_plan(price, snap["atr"], snap["support"], snap["resistance"])

        bar_ts = df.index[-1].to_pydatetime()
        await _upsert_indicator(session, sym.id, bar_ts, snap)
        await _upsert_score(session, sym.id, bar_ts, bd, plan)

        prev_close = quote.prev_close if quote and quote.prev_close else None
        day_change = ((price - prev_close) / prev_close * 100) if prev_close else None
        rows.append({
            "symbol_id": sym.id,
            "ticker": sym.ticker,
            "name": sym.name,
            "sector": sym.sector,
            "price": round(price, 2),
            "day_change_pct": round(day_change, 2) if day_change is not None else None,
            "volume": float(quote.day_volume) if quote and quote.day_volume else
                      float(df["volume"].iloc[-1]),
            "rel_volume": round(snap["rel_volume"], 2) if snap["rel_volume"] else None,
            "atr_pct": round(snap["atr_pct"], 2) if snap["atr_pct"] else None,
            "rsi": round(snap["rsi"], 1) if snap["rsi"] is not None else None,
            "trend": bd.trend,
            "swing_score": bd.total,
            "momentum_pts": bd.momentum, "volatility_pts": bd.volatility,
            "volume_pts": bd.volume, "breakout_pts": bd.breakout,
            "options_pts": bd.options, "catalyst_pts": bd.catalyst,
            "setup_label": bd.setup_label,
            "reasons": bd.reasons,
            "entry": plan.entry if plan else None,
            "entry_high": plan.entry_high if plan else None,
            "stop": plan.stop if plan else None,
            "target": plan.target if plan else None,
            "risk_pct": plan.risk_pct if plan else None,
            "reward_pct": plan.reward_pct if plan else None,
            "rr_ratio": plan.rr_ratio if plan else None,
            "support": snap["support"], "resistance": snap["resistance"],
            "unusual_options": bool(options.unusual) if options else False,
            "updated_at": now.isoformat(),
        })

    await session.commit()
    rows.sort(key=lambda r: r["swing_score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


async def _upsert_indicator(session: AsyncSession, symbol_id: int, ts, snap: dict) -> None:
    await session.execute(delete(IndicatorValue).where(
        IndicatorValue.symbol_id == symbol_id, IndicatorValue.ts == ts))
    session.add(IndicatorValue(
        symbol_id=symbol_id, ts=ts, rsi=snap["rsi"], macd=snap["macd"],
        macd_signal=snap["macd_signal"], ema20=snap["ema20"], ema50=snap["ema50"],
        ema200=snap["ema200"], bb_upper=snap["bb_upper"], bb_lower=snap["bb_lower"],
        atr=snap["atr"], atr_pct=snap["atr_pct"], avg_volume=snap["avg_volume"],
        rel_volume=snap["rel_volume"], support=snap["support"],
        resistance=snap["resistance"],
    ))


async def _upsert_score(session: AsyncSession, symbol_id: int, ts, bd, plan) -> None:
    await session.execute(delete(Score).where(
        Score.symbol_id == symbol_id, Score.ts == ts))
    session.add(Score(
        symbol_id=symbol_id, ts=ts, swing_score=bd.total, momentum_pts=bd.momentum,
        volatility_pts=bd.volatility, volume_pts=bd.volume, breakout_pts=bd.breakout,
        options_pts=bd.options, catalyst_pts=bd.catalyst, trend=bd.trend,
        setup_label=bd.setup_label,
        entry=plan.entry if plan else None, entry_high=plan.entry_high if plan else None,
        stop=plan.stop if plan else None, target=plan.target if plan else None,
        risk_pct=plan.risk_pct if plan else None,
        reward_pct=plan.reward_pct if plan else None,
        rr_ratio=plan.rr_ratio if plan else None,
    ))


async def publish_scores(session: AsyncSession, rows: list[dict]) -> None:
    """Cache the fresh scanner, evaluate alerts against the previous cycle,
    then advance the previous-cycle state."""
    prev_rows_list = await cache_get_json(PREV_ROWS_KEY) or []
    prev_rows = {r["ticker"]: r for r in prev_rows_list}
    prev_top20 = {r["ticker"] for r in prev_rows_list if r.get("rank", 999) <= 20}

    await cache_set_json(SCANNER_KEY, rows)
    fired = await evaluate_alerts(session, rows, prev_rows, prev_top20)
    await cache_set_json(PREV_ROWS_KEY, rows)
    await publish_event("scanner", {"count": len(rows), "top": rows[:20]})
    if fired:
        log.info("%d alerts fired", fired)
