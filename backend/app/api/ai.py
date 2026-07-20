from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.symbols import _get_symbol
from app.db.base import get_db
from app.schemas.core import AIAnalysis
from app.services.ai_analysis import analyze_ticker

router = APIRouter(prefix="/ai", tags=["ai analysis"])


@router.post("/analyze/{ticker}", response_model=AIAnalysis)
async def analyze(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    force: bool = Query(False, description="bypass the daily cache"),
):
    """Generate (or return today's cached) AI analysis for a ticker.

    Works without any key via the sample provider; uses OpenAI when
    AI_PROVIDER=openai and a key is configured."""
    sym = await _get_symbol(db, ticker)
    return await analyze_ticker(db, sym, user=None, force=force)
