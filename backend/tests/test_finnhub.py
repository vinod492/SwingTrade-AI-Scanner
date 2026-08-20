"""Finnhub earnings-calendar adapter: must never raise, must never fabricate
a 'verified' date, must ignore tickers/rows outside what was asked for, and
must distinguish a successful-but-empty result from a failed lookup via the
`ok` flag."""
import httpx
import pytest

from app.providers.finnhub import fetch_earnings_calendar


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestNoKeyConfigured:
    async def test_returns_empty_and_not_ok_without_raising(self, monkeypatch):
        # setenv to "", not delenv: Settings reads FINNHUB_API_KEY from the
        # repo's real .env file too, and env_file is only a fallback for
        # keys absent from os.environ — delenv leaves that fallback in play
        # whenever a real key is configured on disk, silently making this a
        # live network call instead of exercising the no-key path.
        monkeypatch.setenv("FINNHUB_API_KEY", "")
        result, ok = await fetch_earnings_calendar({"AAPL", "MSFT"})
        assert result == []
        assert ok is False


class TestWithKeyConfigured:
    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch):
        monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    async def test_parses_matching_tickers_as_verified(self, monkeypatch):
        payload = {"earningsCalendar": [
            {"symbol": "AAPL", "date": "2026-09-01", "hour": "bmo"},
            {"symbol": "MSFT", "date": "2026-09-05", "hour": "amc"},
            {"symbol": "IGNORED", "date": "2026-09-05", "hour": ""},
        ]}

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_earnings_calendar({"AAPL", "MSFT"})

        assert ok is True
        assert {c.ticker for c in result} == {"AAPL", "MSFT"}
        assert all(c.verified for c in result)
        assert all(c.kind == "earnings" for c in result)
        aapl = next(c for c in result if c.ticker == "AAPL")
        assert "before market open" in aapl.headline
        assert "confirmed" in aapl.headline.lower()

    async def test_rows_missing_date_are_skipped_but_call_is_ok(self, monkeypatch):
        payload = {"earningsCalendar": [{"symbol": "AAPL", "date": None}]}

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_earnings_calendar({"AAPL"})
        assert result == []
        assert ok is True

    async def test_non_200_returns_empty_and_not_ok(self, monkeypatch):
        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(429, text="rate limited", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_earnings_calendar({"AAPL"})
        assert result == []
        assert ok is False

    async def test_network_error_returns_empty_and_not_ok(self, monkeypatch):
        async def fake_get(self, url, params=None, **kwargs):
            raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_earnings_calendar({"AAPL"})
        assert result == []
        assert ok is False

    async def test_malformed_json_returns_empty_and_not_ok(self, monkeypatch):
        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, content=b"not json",
                                  request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_earnings_calendar({"AAPL"})
        assert result == []
        assert ok is False
