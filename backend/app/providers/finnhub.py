"""Finnhub adapters for Catalyst Radar's two cheapest-to-make-real inputs.
Free tier (60 req/min, no card) covers both endpoints used here.

Independent of DATA_PROVIDER: this fills in real dates regardless of which
market-data provider is active, because "when does X report" has nothing
to do with where prices come from. If FINNHUB_API_KEY is unset or a call
fails, callers fall back to the sample generator's clearly-labeled
projection — never silently to a fabricated "real" date.

fetch_earnings_calendar is exhaustive: it returns every company reporting
in the date range, so "ticker not in the response" means "no real earnings
due in this window", not "unknown". Callers use the `ok` flag (not list
truthiness — an empty list is a valid successful result) to tell a
confirmed absence apart from a failed lookup, and treat a successful call
as authoritative for every ticker asked about.

fetch_fda_calendar is NOT exhaustive in the same way — see its docstring.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.providers.base import CatalystInfo

log = logging.getLogger(__name__)

_SESSION_LABELS = {"bmo": "before market open", "amc": "after market close"}

_CORP_SUFFIXES = re.compile(
    r"\b(Inc|Incorporated|Corp|Corporation|Co|Company|Ltd|Group|Holdings?|"
    r"Pharmaceuticals?|Therapeutics|Laboratories|Sciences|Scientific|Health)\b\.?",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^\w\s]")


async def fetch_earnings_calendar(
    tickers: set[str], lookahead_days: int = 45
) -> tuple[list[CatalystInfo], bool]:
    """Real upcoming earnings dates for any ticker in `tickers` within the
    next `lookahead_days`. Returns ([], False) (never raises) if no key is
    configured or the request fails, so callers can unconditionally fall
    back. Returns (rows, True) on a successful call, where `rows` may
    legitimately be empty — that still means "call succeeded, nothing
    upcoming", which callers must treat differently from a failed lookup."""
    settings = get_settings()
    if not settings.finnhub_api_key:
        return [], False

    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=lookahead_days)
    try:
        async with httpx.AsyncClient(base_url="https://finnhub.io/api/v1", timeout=20) as client:
            resp = await client.get("/calendar/earnings", params={
                "from": today.isoformat(), "to": horizon.isoformat(),
                "token": settings.finnhub_api_key,
            })
        if resp.status_code != 200:
            log.warning("finnhub earnings calendar -> %s %s", resp.status_code, resp.text[:200])
            return [], False
        data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("finnhub earnings calendar request failed: %s", exc)
        return [], False
    except ValueError as exc:  # malformed JSON
        log.warning("finnhub earnings calendar returned unparseable body: %s", exc)
        return [], False

    out: list[CatalystInfo] = []
    for item in data.get("earningsCalendar", []) or []:
        symbol = item.get("symbol")
        event_date = item.get("date")
        if symbol not in tickers or not event_date:
            continue
        try:
            when = datetime.fromisoformat(event_date).replace(
                hour=12, minute=0, second=0, tzinfo=timezone.utc)
        except ValueError:
            continue
        session = _SESSION_LABELS.get(item.get("hour", ""), "")
        out.append(CatalystInfo(
            ticker=symbol, kind="earnings",
            headline=f"{symbol} reports earnings {event_date}"
                     + (f" ({session})" if session else "") + " — confirmed date",
            event_date=when, verified=True,
        ))
    return out, True


def _core_company_name(name: str) -> str:
    """Strip common corporate suffixes/punctuation down to the distinctive
    part of a company name, for conservative substring matching against
    free-text FDA meeting descriptions (e.g. "Moderna Inc." -> "Moderna")."""
    stripped = _CORP_SUFFIXES.sub("", name)
    stripped = _NON_WORD.sub(" ", stripped)
    return " ".join(stripped.split())


async def fetch_fda_calendar(
    companies: dict[str, str], lookahead_days: int = 45
) -> tuple[list[CatalystInfo], bool]:
    """FDA advisory committee meetings within the next `lookahead_days`,
    matched to tickers in `companies` (ticker -> company name) by looking
    for each company's distinctive core name in the meeting description.

    This is NOT a per-company PDUFA calendar — the FDA can't publish one;
    an application's existence is confidential until the sponsor discloses
    it. This is FDA's own public advisory-committee meeting calendar, and
    most FDA decisions never go through a committee meeting at all. So
    unlike fetch_earnings_calendar, a successful call here does NOT prove a
    company has nothing pending — an unmatched company is unknown, not
    cleared. Callers must keep sampling for tickers with no match here and
    only replace the ones actually returned (verified=True).

    Matching is deliberately conservative: a meeting only counts as a hit
    when exactly one company's core name appears in its description
    (word-boundary, case-insensitive). Zero matches is the overwhelmingly
    common — and expected — case, since most meetings are general panel
    business with no single company named at all. An ambiguous match
    (more than one company's name appears) is dropped rather than guessed."""
    settings = get_settings()
    if not settings.finnhub_api_key or not companies:
        return [], False

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=lookahead_days)
    try:
        async with httpx.AsyncClient(base_url="https://finnhub.io/api/v1", timeout=20) as client:
            resp = await client.get("/fda-advisory-committee-calendar", params={
                "token": settings.finnhub_api_key,
            })
        if resp.status_code != 200:
            log.warning("finnhub fda calendar -> %s %s", resp.status_code, resp.text[:200])
            return [], False
        data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("finnhub fda calendar request failed: %s", exc)
        return [], False
    except ValueError as exc:  # malformed JSON
        log.warning("finnhub fda calendar returned unparseable body: %s", exc)
        return [], False

    # Skip names too short/generic to match safely (e.g. a one-word core
    # under 4 chars could hit unrelated text).
    cores = {t: c for t, name in companies.items() if len(c := _core_company_name(name)) >= 4}

    out: list[CatalystInfo] = []
    for item in data if isinstance(data, list) else []:
        description = item.get("eventDescription") or ""
        when_raw = item.get("fromDate")
        if not description or not when_raw:
            continue
        try:
            when = datetime.strptime(when_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (now <= when <= horizon):
            continue

        # Match against a punctuation-normalized copy of the description
        # (same normalization _core_company_name applies to the company
        # name), not the raw text — otherwise a name like "Johnson &
        # Johnson" would never match text that spells out the ampersand,
        # since its core name collapses to "Johnson Johnson".
        normalized = " ".join(_NON_WORD.sub(" ", description).split())
        matches = [t for t, core in cores.items()
                   if re.search(rf"\b{re.escape(core)}\b", normalized, re.IGNORECASE)]
        if len(matches) != 1:
            continue  # no match (expected/common) or ambiguous — skip either way
        out.append(CatalystInfo(
            ticker=matches[0], kind="fda_decision",
            headline=f"{description} — confirmed FDA advisory committee meeting",
            event_date=when, verified=True,
        ))
    return out, True
