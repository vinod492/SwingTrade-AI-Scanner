"""Entry / stop / target construction from ATR and support-resistance structure."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TradePlan:
    entry: float
    entry_high: float
    stop: float
    target: float
    risk_pct: float
    reward_pct: float
    rr_ratio: float


def build_trade_plan(
    price: float,
    atr: float | None,
    support: float | None,
    resistance: float | None,
) -> TradePlan | None:
    if price <= 0:
        return None
    atr = atr if atr and atr > 0 else price * 0.02  # sensible default: 2% daily range

    # Entry: buy the breakout trigger when price is coiled just under
    # resistance, otherwise enter around the current zone.
    if resistance is not None and price < resistance <= price * 1.02:
        entry = round(resistance * 1.001, 2)
    else:
        entry = round(price, 2)
    entry_high = round(entry * 1.01, 2)

    # Stop: 1.5×ATR under entry, or just below structural support if that is
    # tighter-but-meaningful. Never risk more than ~15%.
    stop = entry - 1.5 * atr
    if support is not None and support < entry:
        below_support = support * 0.99
        if entry * 0.85 < below_support < stop:
            stop = below_support  # widen to structure only within risk budget
        elif stop < entry * 0.85:
            stop = max(below_support, entry * 0.85)
    stop = round(max(stop, entry * 0.85, 0.01), 2)

    # Target: measured move — at least 2.5×ATR and 2× the risk distance.
    risk_per_share = entry - stop
    target = round(entry + max(2.5 * atr, 2.0 * risk_per_share), 2)

    risk_pct = (entry - stop) / entry * 100
    reward_pct = (target - entry) / entry * 100
    rr = reward_pct / risk_pct if risk_pct > 0 else 0.0
    return TradePlan(
        entry=entry, entry_high=entry_high, stop=stop, target=target,
        risk_pct=round(risk_pct, 2), reward_pct=round(reward_pct, 2),
        rr_ratio=round(rr, 2),
    )
