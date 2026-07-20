"""Technical indicators, vectorized over a daily OHLCV DataFrame.

`compute_indicators` returns a frame aligned to the input with one column per
indicator — the scanner uses the last row, the backtester uses the whole frame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(close.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    return line, line.ewm(span=signal, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0
              ) -> tuple[pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    return mid + num_std * std, mid - num_std * std


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def pivot_levels(df: pd.DataFrame, window: int = 5, lookback: int = 120
                 ) -> tuple[float | None, float | None]:
    """Nearest support below / resistance above the last close, from swing
    pivots (local extremes over ±`window` bars) in the recent `lookback`."""
    recent = df.tail(lookback)
    highs, lows = recent["high"], recent["low"]
    piv_high = highs[(highs == highs.rolling(2 * window + 1, center=True).max())].dropna()
    piv_low = lows[(lows == lows.rolling(2 * window + 1, center=True).min())].dropna()
    price = float(recent["close"].iloc[-1])

    res_candidates = [p for p in piv_high if p > price]
    sup_candidates = [p for p in piv_low if p < price]
    resistance = min(res_candidates) if res_candidates else float(recent["high"].tail(60).max())
    support = max(sup_candidates) if sup_candidates else float(recent["low"].tail(20).min())
    return support, resistance


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Input: OHLCV(+vwap) frame, oldest first. Output aligned indicator frame."""
    out = pd.DataFrame(index=df.index)
    close, volume = df["close"], df["volume"]

    out["ema20"] = ema(close, 20)
    out["ema50"] = ema(close, 50)
    out["ema200"] = ema(close, 200) if len(df) >= 200 else np.nan
    out["rsi"] = rsi(close)
    out["macd"], out["macd_signal"] = macd(close)
    out["bb_upper"], out["bb_lower"] = bollinger(close)

    out["atr"] = atr(df)
    out["atr_avg"] = out["atr"].rolling(20).mean()
    out["atr_pct"] = out["atr"] / close * 100

    out["avg_volume"] = volume.rolling(20).mean().shift(1)  # exclude today
    out["rel_volume"] = volume / out["avg_volume"]

    day_range = df["high"] - df["low"]
    out["range_expansion"] = day_range / day_range.rolling(20).mean().shift(1)

    # Rolling structure (shifted so "today" isn't its own resistance) — used by
    # scoring and the vectorized backtester.
    out["high_20"] = df["high"].rolling(20).max().shift(1)
    out["low_20"] = df["low"].rolling(20).min().shift(1)
    out["new_high_20"] = close > out["high_20"]

    out["close"] = close
    out["volume"] = volume
    return out


def latest_snapshot(df: pd.DataFrame) -> dict:
    """Indicator dict for the most recent bar, with pivot-based S/R."""
    ind = compute_indicators(df)
    row = ind.iloc[-1]
    support, resistance = pivot_levels(df)

    def val(x):
        return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)

    return {
        "rsi": val(row["rsi"]),
        "macd": val(row["macd"]),
        "macd_signal": val(row["macd_signal"]),
        "ema20": val(row["ema20"]),
        "ema50": val(row["ema50"]),
        "ema200": val(row["ema200"]),
        "bb_upper": val(row["bb_upper"]),
        "bb_lower": val(row["bb_lower"]),
        "atr": val(row["atr"]),
        "atr_avg": val(row["atr_avg"]),
        "atr_pct": val(row["atr_pct"]),
        "avg_volume": val(row["avg_volume"]),
        "rel_volume": val(row["rel_volume"]),
        "range_expansion": val(row["range_expansion"]),
        "high_20": val(row["high_20"]),
        "new_high_20": bool(row["new_high_20"]),
        "recent_vol_spike": bool((ind["rel_volume"].tail(3) > 2.5).any()),
        "support": val(support),
        "resistance": val(resistance),
        "close": val(row["close"]),
    }
