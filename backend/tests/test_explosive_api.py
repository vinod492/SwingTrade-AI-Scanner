"""Catalyst Radar API tests against directly-seeded rows (Redis is off in
tests, so these exercise the database fallback path)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.db.base import get_session_factory
from app.db.models import ExplosiveSignal, Symbol

NOW = datetime(2026, 8, 19, tzinfo=timezone.utc)


async def seed_signals(spec: dict[str, dict]) -> None:
    """spec: {ticker: {score, kind, days}}."""
    async with get_session_factory()() as s:
        await s.execute(delete(ExplosiveSignal))
        symbols = {sym.ticker: sym for sym in (await s.execute(
            select(Symbol).where(Symbol.ticker.in_(spec))
        )).scalars()}
        for ticker, spec_row in spec.items():
            sym = symbols[ticker]
            s.add(ExplosiveSignal(
                symbol_id=sym.id, ts=NOW, explosive_score=spec_row["score"],
                catalyst_pts=20, squeeze_pts=10, float_pts=5, iv_pts=8, volume_pts=5,
                catalyst_kind=spec_row["kind"],
                catalyst_headline=f"{ticker} catalyst",
                catalyst_date=NOW + timedelta(days=spec_row["days"]),
                reasons=[f"{ticker} reason"],
            ))
        await s.commit()


@pytest.fixture()
async def seeded(client):
    await seed_signals({
        "NVDA": {"score": 78, "kind": "trial_readout", "days": 2},
        "AAPL": {"score": 45, "kind": "fda_decision", "days": 20},
        "TSLA": {"score": 30, "kind": "earnings", "days": 40},
    })
    return client


class TestCatalystRadar:
    async def test_rows_ranked_by_score(self, seeded):
        r = await seeded.get("/explosive")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert [row["ticker"] for row in body["rows"]] == ["NVDA", "AAPL", "TSLA"]
        assert body["rows"][0]["rank"] == 1
        assert body["rows"][0]["catalyst_kind"] == "trial_readout"

    async def test_min_score_filter(self, seeded):
        r = await seeded.get("/explosive", params={"min_score": 50})
        assert [row["ticker"] for row in r.json()["rows"]] == ["NVDA"]

    async def test_kind_filter(self, seeded):
        r = await seeded.get("/explosive", params={"kind": "fda_decision"})
        assert [row["ticker"] for row in r.json()["rows"]] == ["AAPL"]

    async def test_max_days_filter(self, seeded):
        r = await seeded.get("/explosive", params={"max_days": 10})
        assert [row["ticker"] for row in r.json()["rows"]] == ["NVDA"]

    async def test_days_to_catalyst_computed(self, seeded):
        # NOW is a fixed constant; `days_to_catalyst` is computed against the
        # real clock, so allow slack for whenever the test actually runs.
        r = await seeded.get("/explosive")
        row = next(row for row in r.json()["rows"] if row["ticker"] == "NVDA")
        assert 0 <= row["days_to_catalyst"] <= 2

    async def test_no_auth_required(self, client):
        assert (await client.get("/explosive")).status_code == 200
