# SwingTrade AI Scanner

Scans the US stock market, computes a **0–100 Swing Score** for every symbol, and surfaces
the best swing-trade candidates (2-day to 4-week holding period) with complete trade plans —
entry zone, stop, target, risk/reward — plus live alerts, AI-generated analysis, a strategy
backtester, watchlists with P/L tracking, and user accounts.

> **Research tool only — not financial advice.** Signals are heuristics over market data;
> nothing here should be treated as a recommendation to buy or sell anything.

![stack](https://img.shields.io/badge/stack-FastAPI%20·%20PostgreSQL%20·%20Redis%20·%20arq%20·%20React%20·%20TypeScript%20·%20Tailwind-1c2530)

## Feature tour

| Feature | Where |
|---|---|
| **Market Scanner** — ranked table: price, day %, volume, relative volume, ATR %, RSI, trend, Swing Score, entry/stop/target, R/R; filter by score, sector, RelVol; sortable; live-updating | `/` |
| **Trade Ideas** — top setups as cards in spec format (setup label, entry zone, stop, target, risk %, reward %, score) | `/ideas` |
| **Idea detail** — TradingView-style candlestick chart (lightweight-charts) with EMA 20/50/200 + Bollinger overlays, entry/stop/target price lines, score component breakdown, catalysts, on-demand AI analysis | `/idea/NVDA` |
| **Alerts** — top-20 entry, RelVol > 3x, breakout, RSI crosses 50, unusual options; per-user toggles, event feed, live WebSocket toasts | `/alerts` |
| **Backtesting** — entry rules (min score, min RelVol, above EMA, RSI band) and exits (stop %, target %, max hold); win rate, avg return, max drawdown, Sharpe, equity curve, full trade list | `/backtest` |
| **Watchlist** — track tickers, entries, shares, live P/L | `/watchlist` |
| **Auth & API keys** — JWT accounts; personal provider keys encrypted at rest (Fernet) | `/login`, `/settings` |
| **API documentation** — OpenAPI/Swagger | `http://localhost:8000/docs` |

## Architecture

```
┌────────────┐   REST /api/v1   ┌─────────────┐        ┌──────────────┐
│  React SPA │◄────────────────►│  FastAPI    │◄──────►│  PostgreSQL  │
│ (Vite, TS) │◄──── /ws ───────►│  (async)    │        │  (SQLite in  │
└────────────┘   WebSocket      └──────▲──────┘        │   local dev) │
                                       │ Redis pub/sub └──────▲───────┘
                                ┌──────┴──────┐               │
                                │    Redis    │               │
                                │ cache+queue │               │
                                └──────▲──────┘               │
                                       │ arq jobs + cron      │
                                ┌──────┴──────────────────────┴─┐
                                │ Worker: ingest → indicators → │
                                │ score → trade plan → alerts   │
                                └──────▲────────────────────────┘
                                       │ pluggable providers
                     ┌─────────────────┼──────────────────┐
              ┌──────┴─────┐   ┌───────┴──────┐   ┌───────┴──────┐
              │   sample   │   │ Massive      │   │    Alpaca    │
              │ (synthetic,│   │ (Polygon.io) │   │  (IEX feed)  │
              │  no keys)  │   └──────────────┘   └──────────────┘
              └────────────┘
```

Every scan cycle (default 60s): refresh quotes → refresh options/catalysts → compute
indicators (RSI, MACD, EMA 20/50/200, Bollinger, ATR, average/relative volume, VWAP,
pivot support/resistance) → Swing Score → trade plan → persist + cache in Redis →
evaluate alert rules → push WebSocket events.

## Quickstart

### Option A — Docker (Postgres + Redis, production-style)

```bash
cp .env.example .env          # optionally add keys; runs fully without any
docker compose up --build
```

- Dashboard: http://localhost:8080
- API + docs: http://localhost:8000/docs

### Option B — local dev (SQLite + local Redis, no Docker)

```bash
# backend (Python 3.11+)
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
redis-server --daemonize yes                      # optional but recommended
.venv/bin/uvicorn app.main:app --port 8000        # terminal 1 — API
.venv/bin/arq app.workers.worker.WorkerSettings   # terminal 2 — worker

# frontend
cd frontend
npm install
npm run dev                                       # terminal 3 → http://localhost:5173
```

Tables are created and the ~150-ticker universe seeded automatically on first start
(Alembic migrations are authoritative in Docker; local dev also works with zero setup).
Without Redis the API still serves everything from the database — you lose live pushes
and the hot cache, and the worker requires Redis (arq) to run.

### Sample data mode (default, zero keys)

`DATA_PROVIDER=sample` generates a deterministic synthetic market: per-ticker seeded
random walks with trending/basing/breakout regimes, volume spikes, options flow and
catalysts. The same ticker always tells the same story, alerts demonstrably fire, and
backtests have two years of daily history to chew on. Ideal for development, demos and CI.

## Market data providers

Set `DATA_PROVIDER` in `.env`:

| Provider | Env value | Free tier notes |
|---|---|---|
| Sample (synthetic) | `sample` | No keys. Deterministic, always-interesting data. |
| **Massive** (formerly Polygon.io) | `polygon` | Free key = 5 requests/min, end-of-day data. The adapter **detects your tier at startup**: with a free key it runs in EOD mode (grouped-daily whole-market bars in one call, per-ticker history backfill batched a few symbols per cycle); paid tiers unlock intraday snapshots and options flow automatically. 429s are retried with backoff; a token-bucket limiter enforces `POLYGON_RPM`. |
| Alpaca Market Data | `alpaca` | Free paper account includes IEX real-time quotes + historical bars via multi-symbol endpoints — the best free choice for near-real-time scanning. |

Feeds a key's tier can't serve (e.g. options flow on free tiers) are synthesized from the
sample generator so the scoring pipeline is never starved — the UI footer notes this.
With a free Massive key, expect the first full 150-symbol history backfill to take
~30 minutes (5 req/min); the scanner fills in progressively and deepens each cycle.

AI analysis: `AI_PROVIDER=sample` (templated from real indicator values, no key) or
`AI_PROVIDER=openai` + `OPENAI_API_KEY`. Users can also save a personal OpenAI key in
Settings (encrypted with Fernet; overrides the server key for their analyses).

## Swing Score (0–100)

| Component | Max | Criteria |
|---|---|---|
| Momentum | 20 | price > EMA20 (8) · MACD above signal (7) · RSI 45–70 (5) |
| Volatility | 20 | ATR > 20-day ATR average (8) · IV rising (6) · daily range expanding (6) |
| Volume | 15 | RelVol scaled 1x→2x (0→10) · unusual volume spike (5) |
| Breakout | 20 | at/near resistance breakout (10) · volume confirmation (5) · new 20-day high (5) |
| Options | 15 | unusual call volume (6) · OI increasing (5) · put/call < 0.7 (4) |
| Catalyst | 10 | earnings within 14 days (4) · analyst upgrade (3) · positive news sentiment (3) |

Trade plan: entry at the breakout trigger (or current zone), stop at 1.5×ATR below entry
(widened to structural support only within a 15% risk budget), target at the greater of
2.5×ATR and 2× the risk distance — so R/R is always ≥ 2:1.

## Backtester assumptions

- Signals evaluated per historical day from **price/volume-based score components**
  (options/catalyst history isn't stored per-day), rescaled to 0–100 so thresholds like
  "score > 80" behave as expected.
- Fills at **next day's open**; within a bar the **stop is checked before the target**
  (conservative); time exit after `max_hold_days`.
- Portfolio metrics compound equal capital per trade in exit order; Sharpe is annualized
  from per-trade returns and average holding period. Standard signal-quality
  simplifications — not broker-accurate portfolio simulation.

## Scaling to thousands of tickers

- Ingestion is **budgeted per cycle** and batched (multi-symbol endpoints where the
  provider supports them); backfill deepens progressively under the rate limiter.
- Scanner reads are served from a Redis snapshot (`swingtrade:scanner:latest`) — API
  latency is independent of universe size; the DB fallback keeps working without Redis.
- Workers are stateless arq consumers — run several `worker` replicas to shard cycles;
  candles are indexed on `(symbol_id, timeframe, ts)` and partition-ready.
- WebSocket fan-out is Redis pub/sub, so any number of API replicas can broadcast.

## Tests

```bash
cd backend && .venv/bin/pytest        # 71 tests: indicators (known-value), scoring
                                      # weights, trade-plan math, backtest simulation,
                                      # auth/scanner/watchlist/backtest APIs, alert engine
cd frontend && npm test               # vitest: formatting utilities
```

## Project layout

```
backend/
  app/config.py            env-driven settings
  app/db/                  SQLAlchemy models · Alembic · universe seed
  app/providers/           base ABCs · sample · polygon (Massive) · alpaca · openai
  app/services/            indicators · scoring · trade_plan · alerts · backtest ·
                           ai_analysis · scanner_service · cache · security
  app/workers/             arq worker · ingestion · scoring pipeline
  app/api/                 auth · scanner · symbols · ideas · ai · alerts ·
                           watchlist · backtests · settings
  tests/
frontend/
  src/api/                 typed client · React Query hooks · WebSocket provider
  src/components/          layout · chart panel (lightweight-charts) · display atoms
  src/pages/               Scanner · Ideas · IdeaDetail · Alerts · Watchlist ·
                           Backtest · Login · Settings
```

## Environment variables

See [.env.example](.env.example) — every variable documented, all optional.
Secrets (`.env`) are gitignored; user-saved API keys are Fernet-encrypted at rest.
