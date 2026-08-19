"""Catalyst Radar scoring — a move-*magnitude* score, not a direction score.

This is deliberately not "Swing Score, but for gap-ups." A real binary event
(a Phase 3 readout, an FDA decision, an earnings surprise) can go either way;
nothing in market or options data tells you which before it happens. What
this *can* honestly flag is the setup that makes a big move — up or down —
more likely than usual on the day the outcome lands: a scheduled catalyst
plus crowded positioning (heavy short interest, thin float, options pricing
in a big swing, volume already building). See README for the full reasoning
and MRNA's 2026-08-19 melanoma-trial gap as the motivating example.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

CATALYST_LOOKAHEAD_DAYS = 45
BINARY_CATALYST_KINDS = {"earnings", "trial_readout", "fda_decision"}
CATALYST_LABELS = {
    "earnings": "Earnings report",
    "trial_readout": "Clinical trial readout",
    "fda_decision": "FDA decision (PDUFA date)",
}


@dataclass(slots=True)
class ExplosiveBreakdown:
    catalyst: float = 0.0
    squeeze: float = 0.0
    float_amp: float = 0.0
    iv: float = 0.0
    volume: float = 0.0
    catalyst_kind: str = ""
    catalyst_headline: str = ""
    catalyst_date: datetime | None = None
    days_to_catalyst: int | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            self.catalyst + self.squeeze + self.float_amp + self.iv + self.volume, 1
        )


def _nearest_binary_catalyst(catalysts, now: datetime):
    """Soonest upcoming earnings/trial/FDA event within the lookahead window.
    Analyst notes and same-day news don't count — they aren't scheduled,
    outcome-unknown events."""
    horizon = now + timedelta(days=CATALYST_LOOKAHEAD_DAYS)
    candidates = [
        c for c in catalysts
        if c.kind in BINARY_CATALYST_KINDS and c.event_date is not None
        and now <= c.event_date <= horizon
    ]
    return min(candidates, key=lambda c: c.event_date) if candidates else None


def score_explosive(
    catalysts: list,
    short_pct_float: float | None,
    days_to_cover: float | None,
    iv_rank: float | None,
    iv_rising: bool,
    float_shares: float | None,
    rel_volume: float | None,
    rel_volume_trend_up: bool,
    now: datetime | None = None,
) -> ExplosiveBreakdown:
    """`catalysts` is a list of CatalystInfo-like objects (kind, event_date,
    headline). `iv_rank` is a 0-100 percentile of current IV vs. its own
    trailing history (see iv_rank_percentile)."""
    now = now or datetime.now(timezone.utc)
    bd = ExplosiveBreakdown()
    note = bd.reasons.append

    # ── Catalyst proximity (max 30) ─────────────────────────────────────
    nearest = _nearest_binary_catalyst(catalysts, now)
    if nearest is not None:
        days = max(0, (nearest.event_date - now).days)
        bd.catalyst_kind = nearest.kind
        bd.catalyst_headline = nearest.headline
        bd.catalyst_date = nearest.event_date
        bd.days_to_catalyst = days
        if days <= 3:
            bd.catalyst = 30
        elif days <= 7:
            bd.catalyst = 25
        elif days <= 14:
            bd.catalyst = 18
        elif days <= 30:
            bd.catalyst = 10
        else:
            bd.catalyst = 5
        label = CATALYST_LABELS.get(nearest.kind, nearest.kind)
        note(f"{label} in {days} day{'s' if days != 1 else ''} — outcome unknown")

    # ── Short squeeze setup (max 25) ────────────────────────────────────
    if short_pct_float is not None:
        if short_pct_float >= 30:
            bd.squeeze += 18
            note(f"Short interest {short_pct_float:.0f}% of float — heavily shorted")
        elif short_pct_float >= 20:
            bd.squeeze += 13
            note(f"Short interest {short_pct_float:.0f}% of float")
        elif short_pct_float >= 10:
            bd.squeeze += 6
            note(f"Short interest {short_pct_float:.0f}% of float")
        if (days_to_cover or 0) >= 5 and short_pct_float >= 10:
            bd.squeeze += 7
            note(f"{days_to_cover:.1f} days to cover — shorts would jam the exits")
    bd.squeeze = min(bd.squeeze, 25.0)

    # ── Float / size amplifier (max 15) ─────────────────────────────────
    if float_shares is not None:
        if float_shares < 30e6:
            bd.float_amp = 15
            note("Very small float — outsized moves per share traded")
        elif float_shares < 75e6:
            bd.float_amp = 10
            note("Small float amplifies buy/sell pressure")
        elif float_shares < 150e6:
            bd.float_amp = 5

    # ── Options / IV positioning (max 20) ───────────────────────────────
    if iv_rank is not None:
        bd.iv += round(min(iv_rank, 100) / 100 * 14, 1)
        if iv_rank >= 70:
            note(f"IV rank {iv_rank:.0f} — options market pricing a big move")
    if iv_rising:
        bd.iv += 6
        note("Implied volatility climbing")
    bd.iv = min(bd.iv, 20.0)

    # ── Pre-event volume build (max 10) ─────────────────────────────────
    if (rel_volume or 0) >= 1.5:
        bd.volume += 5
        note(f"Relative volume {rel_volume:.1f}x above normal")
    if rel_volume_trend_up:
        bd.volume += 5
        note("Volume building over the past few sessions")
    bd.volume = min(bd.volume, 10.0)

    return bd


def iv_rank_percentile(history: list[float], latest: float | None) -> float | None:
    """Percentile rank (0-100) of `latest` within trailing `history` values.
    Needs at least a handful of data points to mean anything."""
    if latest is None or len(history) < 5:
        return None
    below = sum(1 for v in history if v <= latest)
    return round(below / len(history) * 100, 1)
