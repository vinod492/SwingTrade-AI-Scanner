import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Backtest, BacktestTrade, User
from app.schemas.core import BacktestCreate, BacktestOut, BacktestTradeOut
from app.services.cache import get_redis

log = logging.getLogger(__name__)
router = APIRouter(prefix="/backtests", tags=["backtesting"])


def _to_out(bt: Backtest, trades: list[BacktestTrade] | None = None) -> BacktestOut:
    return BacktestOut(
        id=bt.id, name=bt.name, status=bt.status, error=bt.error,
        params=bt.params or {}, results=bt.results, created_at=bt.created_at,
        trades=[BacktestTradeOut(
            ticker=t.ticker, entry_date=t.entry_date, entry_price=t.entry_price,
            exit_date=t.exit_date, exit_price=t.exit_price,
            return_pct=t.return_pct, exit_reason=t.exit_reason,
        ) for t in trades or []],
    )


@router.post("", response_model=BacktestOut, status_code=201)
async def create_backtest(body: BacktestCreate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    bt = Backtest(user_id=user.id, name=body.name,
                  params=body.params.model_dump(), status="pending")
    db.add(bt)
    await db.commit()
    await db.refresh(bt)

    # Prefer the worker (arq via Redis); fall back to running inline so the
    # feature also works in a Redis-less dev setup.
    enqueued = False
    redis = await get_redis()
    if redis is not None:
        try:
            from arq.connections import create_pool, RedisSettings
            from app.config import get_settings

            pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
            await pool.enqueue_job("run_backtest_job", bt.id)
            await pool.aclose()
            enqueued = True
        except Exception as exc:
            log.warning("arq enqueue failed (%s); running backtest inline", exc)
    if not enqueued:
        from app.services.backtest import execute_backtest

        await execute_backtest(db, bt.id)
        await db.refresh(bt)
    return _to_out(bt)


@router.get("", response_model=list[BacktestOut])
async def list_backtests(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    bts = (await db.execute(
        select(Backtest).where(Backtest.user_id == user.id)
        .order_by(Backtest.created_at.desc()).limit(50)
    )).scalars().all()
    return [_to_out(bt) for bt in bts]


@router.get("/{backtest_id}", response_model=BacktestOut)
async def get_backtest(backtest_id: int, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    bt = await db.get(Backtest, backtest_id)
    if bt is None or bt.user_id != user.id:
        raise HTTPException(404, "Backtest not found")
    trades = (await db.execute(
        select(BacktestTrade).where(BacktestTrade.backtest_id == bt.id)
        .order_by(BacktestTrade.entry_date)
    )).scalars().all()
    return _to_out(bt, trades)
