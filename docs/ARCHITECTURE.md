# How SwingTrade AI Scanner works (plain-language guide)

This document explains what the app does and how its pieces fit together,
without assuming any technical background. For the full feature list and
developer-level details, see [README.md](../README.md); for hosting/update
instructions, see [DEPLOY.md](../DEPLOY.md).

## What does this app actually do?

It watches the stock market and looks for stocks that might be good
candidates for a **swing trade** — a trade you hold for a few days to a few
weeks, rather than seconds (day trading) or years (investing).

Every 60 seconds, it:

1. Pulls fresh price and volume data for a list of stocks.
2. Runs a set of well-known technical calculations on each one (things
   professional traders look at — trend direction, momentum, trading volume
   compared to normal, price volatility).
3. Combines those into a single **Swing Score from 0–100** — a rough,
   automated opinion of "how interesting does this setup look right now?"
4. For the best-looking ones, works out a suggested trade plan: where you'd
   enter, where you'd set a stop-loss (get out if it goes wrong), and where
   you'd take profit.
5. Shows all of this on a live-updating website, and can ping you the moment
   something crosses a threshold you care about (e.g. "volume just spiked").

It also lets you keep a watchlist, log hypothetical trades, and "backtest" a
strategy — replay it against past data to see how it would have performed.

> This is a research/hobby tool, not financial advice. The score is a
> heuristic (a rule-of-thumb calculation), not a prediction.

## The pieces, in everyday terms

Think of the app as a small factory with five workstations, all running on
one rented computer in the cloud (a "droplet" from DigitalOcean — really just
someone else's server you pay a few dollars a month for).

| Piece | What it's actually doing | Everyday analogy |
|---|---|---|
| **Frontend** | The website you see and click | The shop window / storefront |
| **API** | Answers requests from the website ("give me the latest scores", "log me in") | The shopkeeper taking your order |
| **Worker** | Runs in the background, continuously fetching data and recalculating scores, whether or not anyone is looking at the site | The kitchen, cooking whether or not customers are in the dining room |
| **Database (PostgreSQL)** | Permanent storage — stock history, your account, your watchlist | The filing cabinet — nothing is lost when things restart |
| **Redis** | A fast, short-term scratchpad and message board | A whiteboard used to pass quick notes between workstations, and a big bulletin board where "hey, this alert just fired!" gets posted so the website can show it instantly |

None of these pieces know about the others' internals — they just pass
messages back and forth, which is what makes it possible to restart or
upgrade one piece without taking the whole app down.

## Where does the market data come from?

The app doesn't invent stock prices — it asks a data provider. Right now
it's configured to use a service called **Massive** (formerly known as
Polygon.io), using a free-tier API key. A free key comes with two limits,
which the app is built to work around automatically:

- It can only ask for data a limited number of times per minute (so the app
  paces itself rather than getting blocked).
- Some information (real-time price ticks, options trading data) isn't
  included in the free tier. Where that's missing, the app quietly fills the
  gap with realistic simulated data, so nothing breaks — it just clearly
  labels which parts are real and which are estimated.

If the account is ever upgraded to a paid tier, the app detects that
automatically and starts using real data for those parts too — no code
changes needed, just an upgrade on Massive's side.

## Where does it physically run, and how do people reach it?

```
 You, in a browser
        │
        │  type: swingscanner.app
        ▼
 Cloudflare
 (a free service that (a) looks after the "swingscanner.app" address like a
  phone book, and (b) provides the padlock/https security)
        │
        ▼
 One small rented server ("the droplet"), always on
        │
        ▼
 A doorman program called Caddy
 (listens for incoming visitors and sends them to the right room)
        │
        ├── the website  → Frontend workstation
        └── api.swingscanner.app → API workstation (used for direct/API access)
                   │
                   ▼
        Behind the scenes: API, Worker, Database, and the scratchpad/bulletin
        board (Redis) all run in their own sealed, restartable boxes
        ("containers") on that same one server.
```

Everything — the website, the brain, the filing cabinet, the scratchpad —
currently lives on that single rented server. That's a deliberate,
cost-saving choice for personal use: it costs about $6/month total. The
tradeoff is that if that one server has a problem, everything pauses at
once — acceptable for a personal project, but something a business-critical
product would want to change (by spreading things across multiple servers).
There's already a documented plan for that upgrade path if it's ever needed —
see the "Phase 2" section of
[docs/plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md](plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md).

## What happens when the app is updated?

1. A change is made to the app's code and saved to GitHub (a service that
   keeps a versioned backup/history of the code).
2. Someone connects to the rented server, tells it to fetch that new code.
3. The affected workstation(s) — say, just the API — get rebuilt and
   restarted with the new code. The others keep running, so there's only a
   few seconds of interruption for the piece that changed.

Step-by-step commands for this are in [DEPLOY.md](../DEPLOY.md).
