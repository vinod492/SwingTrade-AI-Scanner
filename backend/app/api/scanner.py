from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.core import ScannerResponse
from app.services.scanner_service import apply_filters, get_scanner_rows

router = APIRouter(prefix="/scanner", tags=["scanner"])

SORTABLE = {"swing_score", "price", "day_change_pct", "rel_volume", "atr_pct", "rsi",
            "rr_ratio", "ticker", "volume"}


@router.get("", response_model=ScannerResponse)
async def scan(
    db: AsyncSession = Depends(get_db),
    min_score: float | None = Query(None, ge=0, le=100),
    sector: str | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    min_rel_volume: float | None = Query(None, ge=0),
    trend: str | None = None,
    q: str | None = Query(None, max_length=32, description="ticker/name search"),
    sort: str = Query("swing_score"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = await get_scanner_rows(db)
    rows = apply_filters(rows, min_score, sector, min_price, max_price,
                         min_rel_volume, trend, q)
    key = sort if sort in SORTABLE else "swing_score"
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key)), reverse=(order == "desc"))
    generated = rows[0]["updated_at"] if rows else None
    return ScannerResponse(total=len(rows), rows=rows[offset:offset + limit],
                           generated_at=generated)


@router.get("/sectors")
async def sectors(db: AsyncSession = Depends(get_db)) -> list[str]:
    rows = await get_scanner_rows(db)
    return sorted({r["sector"] for r in rows if r["sector"]})
