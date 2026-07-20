"""Idempotent database bootstrap: create tables (dev) and seed the symbol universe."""
import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.base import get_engine, get_session_factory
from app.db.models import Base, Symbol
from app.db.universe import UNIVERSE


async def init_db() -> None:
    """Create any missing tables. Alembic is authoritative in production;
    this makes bare local dev and tests work without a migration step."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_symbols() -> int:
    """Insert any universe tickers not already present. Returns count inserted."""
    async with get_session_factory()() as session:
        existing = set((await session.execute(select(Symbol.ticker))).scalars())
        added = 0
        for ticker, name, sector, mcap_b, float_b in UNIVERSE:
            if ticker in existing:
                continue
            session.add(
                Symbol(
                    ticker=ticker,
                    name=name,
                    sector=sector,
                    market_cap=mcap_b * 1e9,
                    float_shares=float_b * 1e9,
                )
            )
            added += 1
        try:
            await session.commit()
        except IntegrityError:
            # Another process (API vs worker) seeded concurrently — fine.
            await session.rollback()
            return 0
        return added


async def bootstrap() -> None:
    await init_db()
    added = await seed_symbols()
    print(f"database ready — {added} symbols seeded")


if __name__ == "__main__":
    asyncio.run(bootstrap())
