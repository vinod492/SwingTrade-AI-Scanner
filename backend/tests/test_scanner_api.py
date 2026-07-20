"""Scanner/ideas/watchlist API tests against directly-seeded score rows
(Redis is off in tests, so these exercise the database fallback path)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.db.base import get_session_factory
from app.db.models import IndicatorValue, Score, Snapshot, Symbol

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


async def seed_scores(spec: dict[str, float]) -> None:
    """spec: {ticker: swing_score}. Creates snapshot+indicator+score rows."""
    async with get_session_factory()() as s:
        for table in (Score, IndicatorValue, Snapshot):
            await s.execute(delete(table))
        symbols = {sym.ticker: sym for sym in (await s.execute(
            select(Symbol).where(Symbol.ticker.in_(spec))
        )).scalars()}
        for ticker, score in spec.items():
            sym = symbols[ticker]
            s.add(Snapshot(symbol_id=sym.id, price=100.0, prev_close=95.0,
                           day_change_pct=5.26, day_volume=2e6, updated_at=NOW))
            s.add(IndicatorValue(symbol_id=sym.id, ts=NOW, rsi=55.0, rel_volume=2.5,
                                 atr_pct=3.0, support=90.0, resistance=105.0))
            s.add(Score(symbol_id=sym.id, ts=NOW, swing_score=score, trend="Uptrend",
                        setup_label="Bullish continuation breakout", entry=100.0,
                        entry_high=101.0, stop=93.0, target=115.0, risk_pct=7.0,
                        reward_pct=15.0, rr_ratio=2.14, momentum_pts=20,
                        volatility_pts=14, volume_pts=15, breakout_pts=20,
                        options_pts=0, catalyst_pts=0))
        await s.commit()


@pytest.fixture()
async def seeded(client):
    await seed_scores({"NVDA": 87, "AAPL": 55, "TSLA": 72})
    return client


class TestScanner:
    async def test_rows_ranked_by_score(self, seeded):
        r = await seeded.get("/scanner")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert [row["ticker"] for row in body["rows"]] == ["NVDA", "TSLA", "AAPL"]
        assert body["rows"][0]["rank"] == 1
        assert body["rows"][0]["entry"] == 100.0
        assert body["rows"][0]["rr_ratio"] == 2.14

    async def test_min_score_filter(self, seeded):
        r = await seeded.get("/scanner", params={"min_score": 70})
        tickers = [row["ticker"] for row in r.json()["rows"]]
        assert tickers == ["NVDA", "TSLA"]

    async def test_search_filter(self, seeded):
        r = await seeded.get("/scanner", params={"q": "nvidia"})
        assert [row["ticker"] for row in r.json()["rows"]] == ["NVDA"]

    async def test_sort_by_ticker_asc(self, seeded):
        r = await seeded.get("/scanner", params={"sort": "ticker", "order": "asc"})
        assert [row["ticker"] for row in r.json()["rows"]] == ["AAPL", "NVDA", "TSLA"]

    async def test_pagination(self, seeded):
        r = await seeded.get("/scanner", params={"limit": 1, "offset": 1})
        body = r.json()
        assert body["total"] == 3
        assert [row["ticker"] for row in body["rows"]] == ["TSLA"]


class TestIdeas:
    async def test_top_ideas_and_detail(self, seeded):
        r = await seeded.get("/ideas", params={"min_score": 60})
        assert [row["ticker"] for row in r.json()] == ["NVDA", "TSLA"]
        r = await seeded.get("/ideas/nvda")
        assert r.status_code == 200
        assert r.json()["setup_label"] == "Bullish continuation breakout"

    async def test_unknown_idea_404(self, seeded):
        r = await seeded.get("/ideas/ZZZZ")
        assert r.status_code == 404


class TestSymbols:
    async def test_symbol_detail(self, seeded):
        r = await seeded.get("/symbols/NVDA")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "NVIDIA Corp."
        assert body["row"]["swing_score"] == 87

    async def test_unknown_symbol_404(self, seeded):
        assert (await seeded.get("/symbols/NOPE")).status_code == 404


class TestWatchlist:
    async def test_add_list_update_delete_with_pl(self, auth_client):
        await seed_scores({"NVDA": 87})
        r = await auth_client.post("/watchlist", json={
            "ticker": "nvda", "entry_price": 80.0, "shares": 10})
        assert r.status_code == 201, r.text
        item = r.json()
        # snapshot price is 100, entry 80 → +25% and +$200
        assert item["pl_pct"] == pytest.approx(25.0)
        assert item["pl_amount"] == pytest.approx(200.0)

        r = await auth_client.get("/watchlist")
        assert len(r.json()) == 1

        r = await auth_client.post("/watchlist", json={"ticker": "NVDA"})
        assert r.status_code == 400  # duplicate

        r = await auth_client.patch(f"/watchlist/{item['id']}",
                                    json={"entry_price": 120.0})
        assert r.json()["pl_pct"] == pytest.approx(-16.67, abs=0.01)

        assert (await auth_client.delete(f"/watchlist/{item['id']}")).status_code == 204
        assert (await auth_client.get("/watchlist")).json() == []

    async def test_watchlist_requires_auth(self, client):
        assert (await client.get("/watchlist")).status_code == 401


class TestAI:
    async def test_sample_analysis_generated(self, seeded):
        r = await seeded.post("/ai/analyze/NVDA")
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "sample"
        for key in ("why_moving", "bull_case", "bear_case", "technical",
                    "trade_plan", "risk_factors"):
            assert len(body[key]) > 30
        assert "NVDA" in body["why_moving"]
