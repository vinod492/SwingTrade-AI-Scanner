from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.schemas.core import ScannerRow
from app.services.scanner_service import get_scanner_rows

router = APIRouter(prefix="/ideas", tags=["trade ideas"])


@router.get("", response_model=list[ScannerRow])
async def top_ideas(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(None, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
):
    rows = await get_scanner_rows(db)
    limit = limit or get_settings().top_n_ideas
    # Long-side ideas only: skip names the engine explicitly labels as no-setup.
    playable = [r for r in rows
                if r["swing_score"] >= min_score
                and r["setup_label"] != "Downtrend — no long setup"]
    return playable[:limit]


@router.get("/{ticker}", response_model=ScannerRow)
async def idea_detail(ticker: str, db: AsyncSession = Depends(get_db)):
    rows = await get_scanner_rows(db)
    row = next((r for r in rows if r["ticker"] == ticker.upper()), None)
    if row is None:
        raise HTTPException(404, f"No scored idea for {ticker.upper()} yet")
    return row
