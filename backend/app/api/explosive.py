from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.core import ExplosiveResponse
from app.services.explosive_service import get_explosive_rows

router = APIRouter(prefix="/explosive", tags=["catalyst radar"])


@router.get("", response_model=ExplosiveResponse)
async def catalyst_radar(
    db: AsyncSession = Depends(get_db),
    min_score: float = Query(0, ge=0, le=100),
    kind: str | None = Query(None, description="earnings | trial_readout | fda_decision"),
    max_days: int | None = Query(None, ge=0, le=90, description="only catalysts within N days"),
    limit: int = Query(50, ge=1, le=200),
):
    """Stocks with elevated move-*magnitude* potential — a pending binary
    catalyst plus crowded positioning. This ranks how big a move could be,
    not which direction it goes; a real trial/FDA/earnings outcome is
    genuinely unknown in advance."""
    rows = await get_explosive_rows(db)
    rows = [r for r in rows if r["explosive_score"] >= min_score]
    if kind:
        rows = [r for r in rows if r["catalyst_kind"] == kind]
    if max_days is not None:
        rows = [r for r in rows
                if r["days_to_catalyst"] is not None and r["days_to_catalyst"] <= max_days]
    return ExplosiveResponse(total=len(rows), rows=rows[:limit])
