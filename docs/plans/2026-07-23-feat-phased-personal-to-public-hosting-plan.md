---
title: Phased hosting architecture — personal scanner now, public-ready later
type: feat
status: active
date: 2026-07-23
---

# Phased hosting architecture — personal scanner now, public-ready later

## Overview

Deploy SwingTrade so it's reachable as a real website today, at minimal cost, for
personal use — without painting ourselves into a corner if it later needs to support
public sign-ups. The app's existing code (`docker-compose.yml`, `render.yaml`,
`netlify.toml`) already supports both ends of this range; this plan sequences *which*
config to use *when*, and defines the concrete trigger for migrating between them.

## Problem Statement / Motivation

[DEPLOY.md](../../DEPLOY.md) currently recommends Netlify (frontend) + Render Blueprint
(backend: API + worker + managed Postgres + managed Redis) at ~$14/month on
always-on starter plans. That's the right shape for a product with real users, but
it's over-provisioned for a single person scanning ~150 tickers:

- Render's worker has no free tier, and the API free tier sleeps after idle
  (defeats "always-on scanner" for a background job that must run every 60s).
- Managed Postgres + managed Redis as separate billed services is redundant when
  one small box can run all four processes (`docker compose up -d` already does
  this locally per the README's Option A).
- The user explicitly wants low-cost personal use now, with room to scale to
  public later — not "build it twice."

The key architectural fact that makes this safe: the **application code is
identical in both phases**. Docker images, env-var-driven config
([backend/app/config.py](../../backend/app/config.py)), and the Redis-snapshot-based
scanner reads (README "Scaling to thousands of tickers") mean going from
"me" to "the public" is an infrastructure swap, not a rewrite.

## Proposed Solution

### Phase 1 — Personal (target: <$10/month, real HTTPS URL)

Single small VPS running the existing `docker-compose.yml` unmodified — API +
worker + Postgres + Redis all on one box — fronted by Netlify (frontend) +
Cloudflare (free TLS + DNS proxy to the VPS, no cert management).

| Component | Choice | Why |
|---|---|---|
| Frontend | Netlify free tier | Already configured (`netlify.toml`); zero cost |
| Backend (API+worker+DB+Redis) | 1 VPS: Hetzner CX22 (~€4.5/mo) or DigitalOcean Basic (~$6/mo) | Cheapest way to run 4 always-on processes; `docker-compose.yml` already does this |
| TLS + domain for backend | Cloudflare (free plan) proxying to VPS IP | Avoids running/renewing certs by hand; gives a real `https://` and `wss://` origin for the API |
| Market data | `DATA_PROVIDER=polygon`, free Massive key (5 req/min, EOD) | Personal scanner scale doesn't need paid tier; matches README's documented free-tier behavior |
| Backups | Nightly `pg_dump` cron on the VPS to any object storage (or skip — data is fully rebuildable from the market-data provider) | Personal use tolerates rebuilding vs. paying for managed backups |

Steps:
1. Provision the VPS, install Docker, `git clone` the repo, `cp .env.example .env`
   and fill in `POLYGON_API_KEY` + a generated `ENCRYPTION_KEY`.
2. `docker compose up -d` — confirms the existing local-dev path works unchanged
   in production.
3. Point a Cloudflare-proxied subdomain (e.g. `api.yourdomain.com`) at the VPS IP,
   enable "Full" TLS mode.
4. Deploy frontend to Netlify per existing DEPLOY.md Step 2, with
   `netlify.toml` and `VITE_WS_URL` pointed at the Cloudflare subdomain instead
   of a Render URL.
5. Confirm end-to-end: scanner loads, WebSocket alerts fire, `/api/v1/health` is green.

### Phase 2 — Public (triggered by a concrete threshold, not a date)

**Migration trigger:** any one of —
- more than ~5 concurrent non-personal users,
- a need for uptime guarantees / on-call rather than "I'll restart the container",
- worker load requiring more than one scan-cycle replica (README's "shard cycles"
  scaling note).

When triggered, migrate to the **already-committed** [render.yaml](../../render.yaml)
Blueprint: managed Postgres, managed Redis, autoscalable API + worker services.
Because config is env-var driven, this is a redeploy, not a code change:

1. Render → New → Blueprint → point at the same repo. Approve the four resources.
2. Update `netlify.toml` and `VITE_WS_URL` to the new Render URL (same two-line
   change as Phase 1 → Phase 2 migration).
3. Decommission the VPS (or keep it as a staging environment).
4. Add what wasn't needed for personal use:
   - Per-IP/per-user rate limiting on the API (public endpoints, not just the
     Massive-key limiter that already exists).
   - Multiple `worker` replicas (README already documents workers as stateless
     arq consumers — this is a Render dashboard scale-up, no code change).
   - Upgrade `DATA_PROVIDER` to a paid Massive tier or add Alpaca as a second
     provider if intraday data matters for public users.
   - Monitoring/alerting beyond Render's built-in (e.g. Sentry for errors).
   - A basic Terms of Use / "not financial advice" disclosure gate, since the
     README already states this is a research tool, not advice — worth surfacing
     in-product once strangers can sign up.
   - Custom domain on Netlify + Render directly (drop the Cloudflare tunnel from
     Phase 1 — no longer needed once Render terminates TLS itself).

## Technical Considerations

- **No per-user data-provider load**: the scanner computes one shared result set
  cached in Redis (`swingtrade:scanner:latest`) — N public users read the same
  cache, so scaling users doesn't scale Massive API calls. This is what makes
  "personal → public" safe without a data-provider cost cliff.
- **Auth is already multi-tenant**: JWT accounts + per-user encrypted API keys
  already exist (`app/api/auth`, `app/services/security`) — Phase 2 needs no new
  auth work, just infra.
- **Single point of failure in Phase 1 is intentional**: one VPS running Postgres,
  Redis, API, and worker together is a known risk for a public product, but
  acceptable for personal use where a restart is a 1-minute inconvenience, not
  an incident.
- **Cost ceiling check**: Phase 1 stays under $10/month total (VPS only — Netlify
  and Cloudflare free tiers cover the rest). Phase 2 lands close to today's
  DEPLOY.md estimate (~$14/month baseline, scaling with worker replicas and DB size).

## Acceptance Criteria

- [ ] Phase 1: `docker-compose.yml` runs unmodified on a VPS with real domain + HTTPS
- [ ] Phase 1: Netlify frontend reachable publicly, proxying to the VPS backend
- [ ] Phase 1: WebSocket alerts (`wss://`) confirmed working through Cloudflare
- [ ] Phase 1: total recurring cost documented and under $10/month
- [ ] Phase 2 trigger conditions written down (see Migration trigger above) so
      the switch is a deliberate decision, not scope creep
- [ ] Phase 2: `render.yaml` Blueprint deploys without modification when triggered
- [ ] Phase 2: only two files change during migration (`netlify.toml`,
      Netlify env var `VITE_WS_URL`) — confirms the "redeploy not rewrite" claim
- [ ] DEPLOY.md updated to document both phases and the trigger for switching

## Dependencies & Risks

- **Massive free-tier rate limit (5 req/min)**: fine for personal EOD scanning per
  README; if Phase 2 public users expect intraday freshness, this forces the
  paid-tier or Alpaca decision earlier than the trigger conditions above suggest.
- **Cloudflare proxy + WebSockets**: Cloudflare's free plan supports WebSocket
  proxying, but must be explicitly verified during Phase 1 setup (some Cloudflare
  configurations block or buffer `wss://` by default) — call out as a first-deploy
  smoke test, not an assumption.
- **VPS is unmanaged**: OS patching, Docker updates, and disk space are the user's
  responsibility in Phase 1 — acceptable tradeoff for personal cost savings, but
  worth stating explicitly since Render/managed services would handle this.
- **No horizontal scaling in Phase 1**: if usage grows faster than expected
  (e.g. shared with friends), the trigger conditions should be checked proactively
  rather than waiting for visible slowdown.

## Sources & References

- [DEPLOY.md](../../DEPLOY.md) — current Netlify + Render deployment guide
- [docker-compose.yml](../../docker-compose.yml) — Phase 1 base (used unmodified)
- [render.yaml](../../render.yaml) — Phase 2 base (used unmodified)
- [netlify.toml](../../netlify.toml) — frontend config, backend URL swapped between phases
- [README.md](../../README.md) "Scaling to thousands of tickers" section — basis for
  the Phase 2 worker-replica and Redis-snapshot scaling claims
