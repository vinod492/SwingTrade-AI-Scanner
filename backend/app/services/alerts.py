"""Alert rule evaluation, run at the end of every scan cycle.

Rules (per user, toggleable):
  top20_entry     — symbol newly entered the top-20 ranked list
  relvol_3x       — relative volume exceeded threshold (default 3x)
  breakout        — price crossed above the tracked resistance level
  rsi_cross_50    — RSI crossed up through 50
  unusual_options — unusual options activity flagged

Dedup is DB-backed (works without Redis): a rule won't re-fire for the same
symbol within its cooldown.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertEvent, AlertRule
from app.services.cache import publish_event

DEFAULT_RULES = ["top20_entry", "relvol_3x", "breakout", "rsi_cross_50", "unusual_options"]

_COOLDOWN_HOURS = {
    "top20_entry": 24, "relvol_3x": 12, "breakout": 24,
    "rsi_cross_50": 24, "unusual_options": 24,
}


def _triggers(rule: AlertRule, row: dict, prev: dict | None, prev_top20: set[str]) -> str | None:
    """Return the alert message if `rule` fires for scanner `row`, else None."""
    ticker = row["ticker"]
    kind = rule.rule_type
    if kind == "top20_entry":
        if row["rank"] <= 20 and ticker not in prev_top20:
            return (f"{ticker} entered the top 20 (rank {row['rank']}, "
                    f"score {row['swing_score']:.0f})")
    elif kind == "relvol_3x":
        threshold = float(rule.params.get("threshold", 3.0))
        if (row.get("rel_volume") or 0) >= threshold:
            return f"{ticker} relative volume {row['rel_volume']:.1f}x (≥ {threshold:g}x)"
    elif kind == "breakout":
        res = row.get("resistance")
        prev_price, prev_res = (prev or {}).get("price"), (prev or {}).get("resistance")
        if res and row["price"] > res * 0.999 and (
            prev_price is None or prev_res is None or prev_price <= prev_res
        ):
            return f"{ticker} breaking out above resistance {res:.2f} at {row['price']:.2f}"
    elif kind == "rsi_cross_50":
        rsi, prev_rsi = row.get("rsi"), (prev or {}).get("rsi")
        if rsi is not None and prev_rsi is not None and prev_rsi < 50 <= rsi:
            return f"{ticker} RSI crossed above 50 (now {rsi:.0f})"
    elif kind == "unusual_options":
        if row.get("unusual_options"):
            return f"{ticker} unusual options activity (call volume spike)"
    return None


async def evaluate_alerts(
    session: AsyncSession,
    rows: list[dict],
    prev_rows: dict[str, dict],
    prev_top20: set[str],
) -> int:
    """Evaluate all enabled rules against the fresh scanner rows. Persists
    events, publishes them over the WS channel, returns count fired."""
    rules = (await session.execute(
        select(AlertRule).where(AlertRule.enabled == True)  # noqa: E712
    )).scalars().all()
    if not rules:
        return 0

    now = datetime.now(timezone.utc)
    fired = 0
    row_by_ticker = {r["ticker"]: r for r in rows}

    for rule in rules:
        cooldown = now - timedelta(hours=_COOLDOWN_HOURS.get(rule.rule_type, 24))
        recent = set((await session.execute(
            select(AlertEvent.symbol_id).where(
                AlertEvent.rule_id == rule.id,
                AlertEvent.triggered_at > cooldown,
            )
        )).scalars())
        for row in row_by_ticker.values():
            if row["symbol_id"] in recent:
                continue
            message = _triggers(rule, row, prev_rows.get(row["ticker"]), prev_top20)
            if not message:
                continue
            event = AlertEvent(
                rule_id=rule.id, user_id=rule.user_id, symbol_id=row["symbol_id"],
                rule_type=rule.rule_type, message=message, triggered_at=now,
            )
            session.add(event)
            fired += 1
            await publish_event("alert", {
                "ticker": row["ticker"], "rule_type": rule.rule_type,
                "message": message, "user_id": rule.user_id,
                "triggered_at": now.isoformat(),
            })
    await session.commit()
    return fired
