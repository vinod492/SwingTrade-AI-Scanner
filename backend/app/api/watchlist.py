from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Snapshot, Symbol, User, Watchlist, WatchlistItem
from app.schemas.core import WatchlistItemIn, WatchlistItemOut, WatchlistItemUpdate
from app.services.scanner_service import get_scanner_rows

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


async def _default_watchlist(db: AsyncSession, user: User) -> Watchlist:
    wl = (await db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.id)
    )).scalars().first()
    if wl is None:
        wl = Watchlist(user_id=user.id, name="Default")
        db.add(wl)
        await db.commit()
        await db.refresh(wl)
    return wl


async def _item_out(db: AsyncSession, item: WatchlistItem) -> WatchlistItemOut:
    sym = await db.get(Symbol, item.symbol_id)
    snap = await db.get(Snapshot, item.symbol_id)
    price = snap.price if snap else None
    pl_amount = pl_pct = None
    if price is not None and item.entry_price:
        pl_pct = (price - item.entry_price) / item.entry_price * 100
        if item.shares:
            pl_amount = (price - item.entry_price) * item.shares
    rows = await get_scanner_rows(db)
    score = next((r["swing_score"] for r in rows if r["ticker"] == sym.ticker), None)
    return WatchlistItemOut(
        id=item.id, ticker=sym.ticker, name=sym.name,
        entry_price=item.entry_price, shares=item.shares, notes=item.notes,
        price=price, day_change_pct=snap.day_change_pct if snap else None,
        pl_amount=round(pl_amount, 2) if pl_amount is not None else None,
        pl_pct=round(pl_pct, 2) if pl_pct is not None else None,
        swing_score=score, added_at=item.added_at,
    )


@router.get("", response_model=list[WatchlistItemOut])
async def list_items(user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    wl = await _default_watchlist(db, user)
    items = (await db.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)
        .order_by(WatchlistItem.added_at)
    )).scalars().all()
    return [await _item_out(db, i) for i in items]


@router.post("", response_model=WatchlistItemOut, status_code=201)
async def add_item(body: WatchlistItemIn, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    sym = (await db.execute(
        select(Symbol).where(Symbol.ticker == body.ticker.upper())
    )).scalar_one_or_none()
    if sym is None:
        raise HTTPException(404, f"Unknown ticker {body.ticker.upper()}")
    wl = await _default_watchlist(db, user)
    dup = (await db.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id,
                                    WatchlistItem.symbol_id == sym.id)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(400, f"{sym.ticker} is already on the watchlist")
    item = WatchlistItem(watchlist_id=wl.id, symbol_id=sym.id,
                         entry_price=body.entry_price, shares=body.shares,
                         notes=body.notes)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await _item_out(db, item)


@router.patch("/{item_id}", response_model=WatchlistItemOut)
async def update_item(item_id: int, body: WatchlistItemUpdate,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    item = await _owned_item(db, user, item_id)
    if body.entry_price is not None:
        item.entry_price = body.entry_price
    if body.shares is not None:
        item.shares = body.shares
    if body.notes is not None:
        item.notes = body.notes
    await db.commit()
    return await _item_out(db, item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    item = await _owned_item(db, user, item_id)
    await db.delete(item)
    await db.commit()


async def _owned_item(db: AsyncSession, user: User, item_id: int) -> WatchlistItem:
    item = await db.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    wl = await db.get(Watchlist, item.watchlist_id)
    if wl is None or wl.user_id != user.id:
        raise HTTPException(404, "Item not found")
    return item
