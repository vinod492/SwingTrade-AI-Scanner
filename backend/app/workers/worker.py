"""arq worker: recurring scan cycle + on-demand backtests.

Run with:  arq app.workers.worker.WorkerSettings
"""
from __future__ import annotations

import logging

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.db.base import get_session_factory
from app.db.seed import bootstrap
from app.providers.base import get_market_provider
from app.providers.sample import SampleProvider
from app.services.cache import cache_get_json
from app.workers import ingestion
from app.workers.scoring_job import (
    SCANNER_KEY,
    compute_and_store_scores,
    publish_scores,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def run_scan_cycle(ctx: dict) -> str:
    """One full ingestion → scoring → alerts cycle."""
    provider = ctx["provider"]
    sample = ctx["sample"]
    caps = await provider.capabilities()
    settings = get_settings()

    async with get_session_factory()() as session:
        symbols = await ingestion.load_universe(session)
        if not symbols:
            return "no symbols"

        # Budget: sample data is free — backfill everything at once; live keys
        # backfill a rate-limited batch per cycle and deepen over time.
        budget = len(symbols) if provider.name == "sample" else max(2, settings.polygon_rpm)
        backfilled = await ingestion.backfill_history(session, provider, symbols, budget)

        quotes = await ingestion.refresh_quotes(session, provider, symbols, caps)

        prev_scan = await cache_get_json(SCANNER_KEY) or []
        priority = [r["ticker"] for r in prev_scan[:25]] or [s.ticker for s in symbols[:25]]
        options_map = await ingestion.refresh_options(
            session, provider, sample, symbols, caps, priority)
        catalysts_map = await ingestion.refresh_catalysts(
            session, provider, sample, symbols, caps, priority)

        rows = await compute_and_store_scores(session, symbols, quotes, options_map,
                                              catalysts_map)
        await publish_scores(session, rows)

    summary = (f"scored {len(rows)}/{len(symbols)} symbols "
               f"(backfilled {backfilled}, provider={provider.name}"
               f"{', EOD' if caps.eod_only else ''})")
    log.info(summary)
    return summary


async def run_backtest_job(ctx: dict, backtest_id: int) -> str:
    from app.services.backtest import execute_backtest

    async with get_session_factory()() as session:
        return await execute_backtest(session, backtest_id)


async def startup(ctx: dict) -> None:
    await bootstrap()
    ctx["provider"] = get_market_provider()
    ctx["sample"] = SampleProvider()
    log.info("worker up — data provider: %s", ctx["provider"].name)
    # Kick a first cycle immediately instead of waiting for the cron minute.
    try:
        await run_scan_cycle(ctx)
    except Exception:
        log.exception("initial scan cycle failed (will retry on schedule)")


async def shutdown(ctx: dict) -> None:
    for key in ("provider", "sample"):
        if key in ctx:
            await ctx[key].close()


def _interval_minutes() -> set[int]:
    """arq cron is minute-granular; honor SCAN_INTERVAL_SECONDS >= 60."""
    minutes = max(1, get_settings().scan_interval_seconds // 60)
    return set(range(0, 60, minutes))


class WorkerSettings:
    functions = [run_scan_cycle, run_backtest_job]
    cron_jobs = [
        cron(run_scan_cycle, minute=_interval_minutes(), second=5,
             timeout=900, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 1800
