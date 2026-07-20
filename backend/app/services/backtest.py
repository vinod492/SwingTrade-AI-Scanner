"""Vectorized backtester over stored daily history.

Entry signals are evaluated on each historical day using price/volume-based
score components (options flow and catalyst history aren't stored per-day, so
the historical score is the price-based subset rescaled to 0–100 — documented
in the README). Fills are next-day-open, exits check the stop before the
target within a bar (conservative), then a max-holding-day time exit.

Portfolio metrics use equal capital per trade compounded in exit order — a
standard simplification for signal-quality evaluation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Backtest, BacktestTrade, Symbol
from app.services.cache import publish_event
from app.services.indicators import compute_indicators
from app.workers.scoring_job import load_daily_frames

log = logging.getLogger(__name__)

MAX_STORED_TRADES = 500

# Price-based score components max out at 69 of the full 100 (no IV/options/
# catalyst history per-day); rescale so user thresholds like "score > 80" work.
_PRICE_BASED_MAX = 69.0


def historical_scores(ind: pd.DataFrame) -> pd.Series:
    """Per-day swing score (0–100) from price/volume components."""
    close = ind["close"]
    pts = pd.Series(0.0, index=ind.index)
    pts += 8 * (close > ind["ema20"]).astype(float)
    pts += 7 * (ind["macd"] > ind["macd_signal"]).astype(float)
    pts += 5 * ind["rsi"].between(45, 70).astype(float)
    pts += 8 * (ind["atr"] > ind["atr_avg"]).astype(float)
    pts += 6 * (ind["range_expansion"] > 1.2).astype(float)
    relvol = ind["rel_volume"].fillna(0)
    pts += 10 * (relvol - 1).clip(0, 1)
    spike = (relvol > 2.5).rolling(3, min_periods=1).max().fillna(0)
    pts += 5 * spike
    near_res = close >= ind["high_20"] * 0.98
    pts += 10 * near_res.astype(float)
    pts += 5 * (near_res & (relvol > 1.5)).astype(float)
    pts += 5 * ind["new_high_20"].astype(float)
    return (pts / _PRICE_BASED_MAX * 100).clip(0, 100)


def entry_signals(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    signal = historical_scores(ind) >= float(params.get("min_swing_score", 80))
    min_rv = float(params.get("min_rel_volume", 0) or 0)
    if min_rv > 0:
        signal &= ind["rel_volume"].fillna(0) >= min_rv
    ema_span = params.get("price_above_ema")
    if ema_span in (20, 50, 200):
        col = f"ema{ema_span}"
        signal &= df["close"] > ind[col]
    if params.get("rsi_min") is not None:
        signal &= ind["rsi"] >= float(params["rsi_min"])
    if params.get("rsi_max") is not None:
        signal &= ind["rsi"] <= float(params["rsi_max"])
    return signal.fillna(False)


def simulate_symbol(ticker: str, df: pd.DataFrame, params: dict) -> list[dict]:
    """Walk one symbol's history; one open position at a time per symbol."""
    ind = compute_indicators(df)
    signal = entry_signals(df, ind, params)
    stop_pct = float(params.get("stop_loss_pct", 8)) / 100
    target_pct = float(params.get("take_profit_pct", 15)) / 100
    max_hold = int(params.get("max_hold_days", 20))

    opens, highs = df["open"].to_numpy(), df["high"].to_numpy()
    lows, closes = df["low"].to_numpy(), df["close"].to_numpy()
    dates = df.index
    sig = signal.to_numpy()

    trades: list[dict] = []
    i, n = 0, len(df)
    while i < n - 1:
        if not sig[i]:
            i += 1
            continue
        entry_i = i + 1
        entry_price = opens[entry_i]
        stop = entry_price * (1 - stop_pct)
        target = entry_price * (1 + target_pct)
        exit_i, exit_price, reason = None, None, ""
        for j in range(entry_i, min(entry_i + max_hold, n)):
            if lows[j] <= stop:  # stop checked first: conservative fill order
                exit_i, exit_price, reason = j, stop, "stop"
                break
            if highs[j] >= target:
                exit_i, exit_price, reason = j, target, "target"
                break
        if exit_i is None:
            j = min(entry_i + max_hold - 1, n - 1)
            exit_i, exit_price, reason = j, closes[j], "time"
        trades.append({
            "ticker": ticker,
            "entry_date": dates[entry_i].to_pydatetime(),
            "entry_price": round(float(entry_price), 4),
            "exit_date": dates[exit_i].to_pydatetime(),
            "exit_price": round(float(exit_price), 4),
            "return_pct": round(float((exit_price - entry_price) / entry_price * 100), 3),
            "exit_reason": reason,
            "hold_days": int(exit_i - entry_i + 1),
        })
        i = exit_i + 1  # no overlapping positions in the same symbol
    return trades


def aggregate_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"total_trades": 0, "message": "No trades matched the entry rules — "
                "try a lower score threshold or wider filters."}
    rets = np.array([t["return_pct"] for t in trades]) / 100
    wins = int((rets > 0).sum())
    ordered = sorted(trades, key=lambda t: t["exit_date"])
    equity = np.cumprod(1 + np.array([t["return_pct"] for t in ordered]) / 100)
    peak = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak).min()) * 100
    avg_hold = float(np.mean([t["hold_days"] for t in trades]))
    std = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / std * np.sqrt(252 / max(avg_hold, 1))) if std > 0 else None
    return {
        "total_trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": round(wins / len(trades) * 100, 1),
        "avg_return_pct": round(float(rets.mean() * 100), 2),
        "median_return_pct": round(float(np.median(rets) * 100), 2),
        "best_trade_pct": round(float(rets.max() * 100), 2),
        "worst_trade_pct": round(float(rets.min() * 100), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "avg_hold_days": round(avg_hold, 1),
        "total_return_pct": round(float((equity[-1] - 1) * 100), 2),
        "exit_breakdown": {
            reason: sum(1 for t in trades if t["exit_reason"] == reason)
            for reason in ("target", "stop", "time")
        },
        "equity_curve": [
            {"date": t["exit_date"].date().isoformat(), "equity": round(float(e), 4)}
            for t, e in zip(ordered, equity)
        ],
    }


async def execute_backtest(session: AsyncSession, backtest_id: int) -> str:
    bt = await session.get(Backtest, backtest_id)
    if bt is None:
        return f"backtest {backtest_id} not found"
    bt.status = "running"
    await session.commit()
    try:
        params = bt.params or {}
        symbols = list((await session.execute(
            select(Symbol).where(Symbol.active == True)  # noqa: E712
        )).scalars())
        frames = await load_daily_frames(session, [s.id for s in symbols])
        cutoff = pd.Timestamp(
            datetime.now(timezone.utc) - timedelta(days=int(params.get("lookback_days", 365)))
        )
        ticker_by_id = {s.id: s.ticker for s in symbols}

        all_trades: list[dict] = []
        for sid, df in frames.items():
            df = df[df.index >= cutoff]
            if len(df) < 60:
                continue
            all_trades.extend(simulate_symbol(ticker_by_id[sid], df, params))

        bt.results = aggregate_metrics(all_trades)
        bt.status = "done"
        await session.execute(delete(BacktestTrade).where(
            BacktestTrade.backtest_id == bt.id))
        stored = sorted(all_trades, key=lambda t: t["entry_date"])[:MAX_STORED_TRADES]
        session.add_all([
            BacktestTrade(backtest_id=bt.id, ticker=t["ticker"],
                          entry_date=t["entry_date"], entry_price=t["entry_price"],
                          exit_date=t["exit_date"], exit_price=t["exit_price"],
                          return_pct=t["return_pct"], exit_reason=t["exit_reason"])
            for t in stored
        ])
        await session.commit()
        await publish_event("backtest_done", {"id": bt.id, "name": bt.name,
                                              "user_id": bt.user_id})
        return f"backtest {bt.id}: {bt.results.get('total_trades', 0)} trades"
    except Exception as exc:
        log.exception("backtest %d failed", backtest_id)
        bt.status = "error"
        bt.error = str(exc)[:500]
        await session.commit()
        return f"backtest {backtest_id} failed: {exc}"
