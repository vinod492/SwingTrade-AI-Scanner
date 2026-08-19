from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import Candle, Catalyst, Symbol
from app.schemas.core import CandleOut, SymbolDetail
from app.services.indicators import bollinger, ema
from app.services.scanner_service import get_scanner_rows

import pandas as pd

router = APIRouter(prefix="/symbols", tags=["symbols"])


async def _get_symbol(db: AsyncSession, ticker: str) -> Symbol:
    sym = (await db.execute(
        select(Symbol).where(Symbol.ticker == ticker.upper())
    )).scalar_one_or_none()
    if sym is None:
        raise HTTPException(404, f"Unknown ticker {ticker.upper()}")
    return sym


@router.get("/{ticker}", response_model=SymbolDetail)
async def symbol_detail(ticker: str, db: AsyncSession = Depends(get_db)):
    sym = await _get_symbol(db, ticker)
    rows = await get_scanner_rows(db)
    row = next((r for r in rows if r["ticker"] == sym.ticker), None)
    catalysts = (await db.execute(
        select(Catalyst).where(Catalyst.symbol_id == sym.id)
        .order_by(Catalyst.created_at.desc()).limit(10)
    )).scalars().all()
    return SymbolDetail(
        ticker=sym.ticker, name=sym.name, sector=sym.sector,
        market_cap=sym.market_cap, float_shares=sym.float_shares, row=row,
        catalysts=[{
            "kind": c.kind, "headline": c.headline, "sentiment": c.sentiment,
            "event_date": c.event_date.isoformat() if c.event_date else None,
            "verified": c.verified,
        } for c in catalysts],
    )


@router.get("/{ticker}/candles", response_model=list[CandleOut])
async def candles(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    timeframe: str = Query("1d", pattern="^(1d|1h|5m)$"),
    limit: int = Query(300, ge=30, le=1000),
):
    sym = await _get_symbol(db, ticker)
    bars = (await db.execute(
        select(Candle).where(Candle.symbol_id == sym.id, Candle.timeframe == timeframe)
        .order_by(Candle.ts.desc()).limit(limit)
    )).scalars().all()
    bars = list(reversed(bars))
    if not bars:
        return []

    closes = pd.Series([b.close for b in bars])
    e20, e50 = ema(closes, 20), ema(closes, 50)
    e200 = ema(closes, 200) if len(bars) >= 200 else None
    bb_up, bb_lo = bollinger(closes)

    def _f(series, i):
        if series is None:
            return None
        v = series.iloc[i]
        return None if pd.isna(v) else round(float(v), 4)

    return [
        CandleOut(
            ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume,
            ema20=_f(e20, i), ema50=_f(e50, i), ema200=_f(e200, i),
            bb_upper=_f(bb_up, i), bb_lower=_f(bb_lo, i),
        )
        for i, b in enumerate(bars)
    ]
