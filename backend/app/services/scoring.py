"""Swing Score engine — the exact weighting from the product spec (total 100):

Momentum 20 · Volatility 20 · Volume 15 · Breakout 20 · Options 15 · Catalyst 10
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.providers.base import CatalystInfo, OptionsInfo


@dataclass(slots=True)
class ScoreBreakdown:
    momentum: float = 0.0
    volatility: float = 0.0
    volume: float = 0.0
    breakout: float = 0.0
    options: float = 0.0
    catalyst: float = 0.0
    trend: str = "Neutral"
    setup_label: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            self.momentum + self.volatility + self.volume
            + self.breakout + self.options + self.catalyst, 1
        )


def _near_or_above_resistance(price: float, resistance: float | None) -> bool:
    return resistance is not None and price >= resistance * 0.98


def classify_trend(price: float | None, ema20, ema50, ema200) -> str:
    if None in (price, ema20, ema50):
        return "Neutral"
    if ema200 is not None:
        if ema20 > ema50 > ema200 and price > ema20:
            return "Strong Uptrend"
        if ema20 < ema50 < ema200 and price < ema20:
            return "Downtrend"
    if ema20 > ema50 and price > ema20:
        return "Uptrend"
    if ema20 < ema50 and price < ema20:
        return "Downtrend"
    return "Sideways"


def classify_setup(bd: ScoreBreakdown, ind: dict, price: float) -> str:
    trend_up = bd.trend in ("Uptrend", "Strong Uptrend")
    if bd.breakout >= 15 and trend_up:
        return "Bullish continuation breakout"
    if bd.breakout >= 10:
        return "Breakout attempt at resistance"
    if _near_or_above_resistance(price, ind.get("resistance")) and trend_up:
        return "Coiling below resistance"
    rsi = ind.get("rsi")
    if trend_up and rsi is not None and rsi < 45:
        return "Pullback to support in uptrend"
    if trend_up:
        return "Trend continuation"
    if bd.trend == "Downtrend":
        return "Downtrend — no long setup"
    return "Range consolidation"


def score_symbol(
    ind: dict,
    price: float,
    options: OptionsInfo | None = None,
    catalysts: list[CatalystInfo] | None = None,
    now: datetime | None = None,
) -> ScoreBreakdown:
    """`ind` is the dict from indicators.latest_snapshot (or an equivalent
    per-day row in the backtester)."""
    bd = ScoreBreakdown()
    now = now or datetime.now(timezone.utc)
    note = bd.reasons.append

    # ── Momentum (max 20) ───────────────────────────────────────────────
    ema20, rsi = ind.get("ema20"), ind.get("rsi")
    macd_line, macd_sig = ind.get("macd"), ind.get("macd_signal")
    if ema20 is not None and price > ema20:
        bd.momentum += 8
        note("Price above 20 EMA")
    if macd_line is not None and macd_sig is not None and macd_line > macd_sig:
        bd.momentum += 7
        note("MACD above signal (bullish)")
    if rsi is not None and 45 <= rsi <= 70:
        bd.momentum += 5
        note(f"RSI {rsi:.0f} in the 45–70 power zone")

    # ── Volatility (max 20) ─────────────────────────────────────────────
    atr_now, atr_avg = ind.get("atr"), ind.get("atr_avg")
    if atr_now is not None and atr_avg is not None and atr_now > atr_avg:
        bd.volatility += 8
        note("ATR above its 20-day average")
    iv_change = options.iv_change if options else None
    if iv_change is not None and iv_change > 0:
        bd.volatility += 6
        note("Implied volatility rising")
    rng_exp = ind.get("range_expansion")
    if rng_exp is not None and rng_exp > 1.2:
        bd.volatility += 6
        note("Daily range expanding")

    # ── Volume (max 15) ─────────────────────────────────────────────────
    relvol = ind.get("rel_volume")
    if relvol is not None:
        scaled = max(0.0, min(1.0, (relvol - 1.0)))  # 1x → 0, 2x+ → full
        bd.volume += round(10 * scaled, 1)
        if relvol >= 2:
            note(f"Relative volume {relvol:.1f}x")
    if ind.get("recent_vol_spike"):
        bd.volume += 5
        note("Unusual volume spike in last 3 sessions")

    # ── Breakout setup (max 20) ─────────────────────────────────────────
    breaking = _near_or_above_resistance(price, ind.get("resistance"))
    if breaking:
        bd.breakout += 10
        note("At/near resistance breakout level")
    if breaking and relvol is not None and relvol > 1.5:
        bd.breakout += 5
        note("Breakout volume confirmation")
    if ind.get("new_high_20"):
        bd.breakout += 5
        note("New 20-day high")

    # ── Options activity (max 15) ───────────────────────────────────────
    if options:
        if options.unusual or (
            options.call_volume and options.avg_call_volume
            and options.call_volume > 2 * options.avg_call_volume
        ):
            bd.options += 6
            note("Unusual call volume")
        if options.oi_change_pct is not None and options.oi_change_pct > 0:
            bd.options += 5
            note("Open interest increasing")
        if options.put_call_ratio is not None and options.put_call_ratio < 0.7:
            bd.options += 4
            note(f"Bullish put/call ratio {options.put_call_ratio:.2f}")

    # ── Catalysts (max 10) ──────────────────────────────────────────────
    for cat in catalysts or []:
        if cat.kind == "earnings" and cat.event_date and \
                now <= cat.event_date <= now + timedelta(days=14):
            bd.catalyst += 4
            note("Earnings inside the swing window")
        elif cat.kind == "upgrade":
            bd.catalyst += 3
            note("Recent analyst upgrade")
        elif cat.kind == "news" and (cat.sentiment or 0) > 0.3:
            bd.catalyst += 3
            note("Positive news sentiment")
    bd.catalyst = min(bd.catalyst, 10.0)

    bd.trend = classify_trend(price, ema20, ind.get("ema50"), ind.get("ema200"))
    bd.setup_label = classify_setup(bd, ind, price)
    return bd
