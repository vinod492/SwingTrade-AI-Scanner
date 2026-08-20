"""Finnhub adapters: must never raise, must never fabricate a 'verified'
date, must ignore tickers/rows outside what was asked for, and must
distinguish a successful-but-empty result from a failed lookup via the
`ok` flag.

fetch_fda_calendar additionally must only attach a meeting to a ticker on
an unambiguous company-name match — no match and multiple matches must
both be dropped, not guessed."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.providers.finnhub import fetch_earnings_calendar, fetch_fda_calendar


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

    async def test_fda_returns_empty_and_not_ok_without_raising(self, monkeypatch):
        monkeypatch.setenv("FINNHUB_API_KEY", "")
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc."})
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


class TestFdaCalendar:
    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch):
        monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    @staticmethod
    def _fmt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    async def test_no_companies_returns_empty_and_not_ok(self, monkeypatch):
        result, ok = await fetch_fda_calendar({})
        assert result == []
        assert ok is False

    async def test_unambiguous_name_match_is_verified(self, monkeypatch):
        soon = datetime.now(timezone.utc) + timedelta(days=10)
        payload = [{
            "fromDate": self._fmt(soon), "toDate": self._fmt(soon),
            "eventDescription": "Moderna Inc. RSV Vaccine Advisory Committee Meeting",
            "url": "https://www.fda.gov/example",
        }]

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc.", "PFE": "Pfizer Inc."})

        assert ok is True
        assert len(result) == 1
        assert result[0].ticker == "MRNA"
        assert result[0].kind == "fda_decision"
        assert result[0].verified is True

    async def test_ampersand_in_company_name_still_matches_raw_text(self, monkeypatch):
        # "Johnson & Johnson" collapses to core name "Johnson Johnson", but
        # real FDA text spells out the ampersand — the description must be
        # normalized the same way before matching, or this would never hit.
        soon = datetime.now(timezone.utc) + timedelta(days=10)
        payload = [{
            "fromDate": self._fmt(soon), "toDate": self._fmt(soon),
            "eventDescription": "Johnson & Johnson Orthopedic Device Panel Meeting",
            "url": "https://www.fda.gov/example",
        }]

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"JNJ": "Johnson & Johnson"})

        assert ok is True
        assert len(result) == 1
        assert result[0].ticker == "JNJ"

    async def test_generic_meeting_with_no_company_named_matches_nothing(self, monkeypatch):
        soon = datetime.now(timezone.utc) + timedelta(days=10)
        payload = [{
            "fromDate": self._fmt(soon), "toDate": self._fmt(soon),
            "eventDescription": "Pediatric Advisory Committee Meeting Announcement",
            "url": "https://www.fda.gov/example",
        }]

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc.", "PFE": "Pfizer Inc."})

        assert ok is True
        assert result == []

    async def test_ambiguous_match_is_dropped_not_guessed(self, monkeypatch):
        soon = datetime.now(timezone.utc) + timedelta(days=10)
        payload = [{
            "fromDate": self._fmt(soon), "toDate": self._fmt(soon),
            "eventDescription": "Joint meeting to discuss Moderna Inc. and Pfizer Inc. vaccine data",
            "url": "https://www.fda.gov/example",
        }]

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc.", "PFE": "Pfizer Inc."})

        assert ok is True
        assert result == []

    async def test_meeting_outside_lookahead_window_is_excluded(self, monkeypatch):
        far = datetime.now(timezone.utc) + timedelta(days=200)
        payload = [{
            "fromDate": self._fmt(far), "toDate": self._fmt(far),
            "eventDescription": "Moderna Inc. RSV Vaccine Advisory Committee Meeting",
            "url": "https://www.fda.gov/example",
        }]

        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc."})

        assert ok is True
        assert result == []

    async def test_non_200_returns_empty_and_not_ok(self, monkeypatch):
        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(429, text="rate limited", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc."})
        assert result == []
        assert ok is False

    async def test_malformed_json_returns_empty_and_not_ok(self, monkeypatch):
        async def fake_get(self, url, params=None, **kwargs):
            return httpx.Response(200, content=b"not json",
                                  request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        result, ok = await fetch_fda_calendar({"MRNA": "Moderna Inc."})
        assert result == []
        assert ok is False
