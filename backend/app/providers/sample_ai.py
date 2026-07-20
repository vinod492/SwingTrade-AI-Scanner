"""Keyless AI analysis: builds a readable, ticker-specific narrative from the
actual indicator/score context. Same output shape as the OpenAI provider."""
from __future__ import annotations

from app.providers.base import AIProvider


def _fmt(value, suffix="", nd=2):
    if value is None:
        return "n/a"
    return f"{value:.{nd}f}{suffix}"


class SampleAIProvider(AIProvider):
    name = "sample"

    async def analyze(self, ctx: dict) -> dict:
        t = ctx.get("ticker", "?")
        price = ctx.get("price")
        rsi, macd, macd_sig = ctx.get("rsi"), ctx.get("macd"), ctx.get("macd_signal")
        ema20, ema50, ema200 = ctx.get("ema20"), ctx.get("ema50"), ctx.get("ema200")
        relvol, atr_pct = ctx.get("rel_volume"), ctx.get("atr_pct")
        score, trend = ctx.get("swing_score"), ctx.get("trend", "Neutral")
        setup = ctx.get("setup_label") or "developing setup"
        entry, stop, target = ctx.get("entry"), ctx.get("stop"), ctx.get("target")
        catalysts = ctx.get("catalysts") or []
        support, resistance = ctx.get("support"), ctx.get("resistance")

        above20 = price is not None and ema20 is not None and price > ema20
        macd_bull = macd is not None and macd_sig is not None and macd > macd_sig
        vol_note = (
            f"Relative volume of {_fmt(relvol, 'x', 1)} shows "
            + ("strong institutional participation." if (relvol or 0) > 2
               else "unremarkable participation so far.")
        )
        cat_note = ("; ".join(c.get("headline", "") for c in catalysts[:2])
                    or "No scheduled catalyst on the calendar.")

        return {
            "why_moving": (
                f"{t} trades at {_fmt(price)} in a {trend.lower()} structure, scored "
                f"{_fmt(score, '', 0)}/100 as a {setup}. {vol_note} {cat_note}"
            ),
            "bull_case": (
                f"Price is {'above' if above20 else 'below'} the 20 EMA ({_fmt(ema20)}) with the "
                f"MACD {'above' if macd_bull else 'below'} its signal line. A push through "
                f"resistance at {_fmt(resistance)} on expanding volume opens the measured move "
                f"toward {_fmt(target)}; ATR of {_fmt(atr_pct, '%', 1)} per day gives the swing "
                f"room to reach it inside a 2–4 week window."
            ),
            "bear_case": (
                f"Failure to hold support at {_fmt(support)} invalidates the setup. "
                f"RSI at {_fmt(rsi, '', 0)} "
                + ("is stretched, so chasing here risks buying a short-term top."
                   if (rsi or 50) > 70 else
                   "leaves momentum unconfirmed — a rejection at resistance likely means more "
                   "basing before a durable move.")
                + " Broad-market weakness would drag beta names regardless of setup."
            ),
            "technical": (
                f"EMA stack: 20={_fmt(ema20)}, 50={_fmt(ema50)}, 200={_fmt(ema200)} "
                f"({trend}). RSI {_fmt(rsi, '', 0)}; MACD {_fmt(macd)} vs signal "
                f"{_fmt(macd_sig)} ({'bullish' if macd_bull else 'bearish'} posture). "
                f"Key levels: support {_fmt(support)}, resistance {_fmt(resistance)}. "
                f"Daily ATR {_fmt(atr_pct, '%', 1)} of price."
            ),
            "trade_plan": (
                f"Enter {_fmt(entry)}–{_fmt(ctx.get('entry_high') or entry)} on strength, "
                f"stop {_fmt(stop)} (below support / 1.5×ATR), target {_fmt(target)}. "
                f"Risk {_fmt(ctx.get('risk_pct'), '%', 1)} against reward "
                f"{_fmt(ctx.get('reward_pct'), '%', 1)} — "
                f"{_fmt(ctx.get('rr_ratio'), ':1', 1)} reward-to-risk. Scale out half at the "
                f"first resistance test and trail the rest."
            ),
            "risk_factors": (
                "Earnings or macro prints inside the holding window can gap through stops; "
                "position-size so the stop distance is a survivable loss. "
                + ("Elevated relative volume cuts both ways — exits get crowded fast. "
                   if (relvol or 0) > 2 else "")
                + "This is generated analysis for research, not financial advice."
            ),
        }
