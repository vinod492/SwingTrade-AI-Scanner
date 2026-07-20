"""AI analysis orchestration: assemble ticker context, cache results, and call
the configured AI provider (a user-saved OpenAI key overrides the global one)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Catalyst, IndicatorValue, Symbol, User, UserApiKey
from app.providers.base import AIProvider, get_ai_provider
from app.services.cache import cache_get_json, cache_set_json
from app.services.scanner_service import get_scanner_rows
from app.services.security import decrypt_secret


def _cache_key(ticker: str) -> str:
    return f"swingtrade:ai:{ticker}:{datetime.now(timezone.utc):%Y%m%d}"


async def build_context(session: AsyncSession, symbol: Symbol) -> dict:
    rows = await get_scanner_rows(session)
    row = next((r for r in rows if r["ticker"] == symbol.ticker), {})
    catalysts = (await session.execute(
        select(Catalyst).where(Catalyst.symbol_id == symbol.id)
        .order_by(Catalyst.created_at.desc()).limit(5)
    )).scalars().all()
    ctx = {
        "ticker": symbol.ticker,
        "company": symbol.name,
        "sector": symbol.sector,
        "catalysts": [{"kind": c.kind, "headline": c.headline, "sentiment": c.sentiment}
                      for c in catalysts],
    }
    for key in ("price", "day_change_pct", "rel_volume", "atr_pct", "rsi", "trend",
                "swing_score", "setup_label", "entry", "entry_high", "stop", "target",
                "risk_pct", "reward_pct", "rr_ratio", "support", "resistance",
                "momentum_pts", "volatility_pts", "volume_pts", "breakout_pts",
                "options_pts", "catalyst_pts", "reasons"):
        ctx[key] = row.get(key)
    ctx["ema20"] = ctx["ema50"] = ctx["ema200"] = None
    ctx["macd"] = ctx["macd_signal"] = None
    latest_ind = (await session.execute(
        select(IndicatorValue).where(IndicatorValue.symbol_id == symbol.id)
        .order_by(IndicatorValue.ts.desc()).limit(1)
    )).scalar_one_or_none()
    if latest_ind:
        ctx.update({
            "ema20": latest_ind.ema20, "ema50": latest_ind.ema50,
            "ema200": latest_ind.ema200, "macd": latest_ind.macd,
            "macd_signal": latest_ind.macd_signal,
        })
    return ctx


async def _provider_for_user(session: AsyncSession, user: User | None) -> AIProvider:
    if user is not None:
        saved = (await session.execute(
            select(UserApiKey).where(UserApiKey.user_id == user.id,
                                     UserApiKey.provider == "openai")
        )).scalar_one_or_none()
        if saved:
            key = decrypt_secret(saved.encrypted_key)
            if key:
                from app.providers.openai_ai import OpenAIProvider

                return OpenAIProvider(api_key=key)
    return get_ai_provider()


async def analyze_ticker(session: AsyncSession, symbol: Symbol,
                         user: User | None = None, force: bool = False) -> dict:
    cache_key = _cache_key(symbol.ticker)
    if not force:
        cached = await cache_get_json(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    provider = await _provider_for_user(session, user)
    ctx = await build_context(session, symbol)
    sections = await provider.analyze(ctx)
    result = {
        "ticker": symbol.ticker,
        **sections,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider.name,
        "cached": False,
    }
    await cache_set_json(cache_key, result, ttl=get_settings().ai_cache_ttl_seconds)
    return result
