# Deploying and updating SwingTrade AI Scanner

> Looking for what the app actually does? See [README.md](README.md) for the
> feature tour, or [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a
> plain-language walkthrough of how it's built.

## Current live setup (as of 2026-07-24)

The app is **live today** at **https://swingscanner.app**, running on a single
DigitalOcean droplet — not the Render split this file used to describe.
That split still exists in the repo ([render.yaml](render.yaml)) as the
documented upgrade path for if the app ever needs to scale beyond personal
use — see
[docs/plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md](docs/plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md).
For now, everything below is what's actually running.

```
Cloudflare (DNS + free HTTPS certificate, in front of everything)
        │
        ▼
DigitalOcean droplet (157.245.89.255)
        │
        ▼
  Caddy (reverse proxy, listens on 80/443)
        │
        ├── swingscanner.app        → docker container "frontend" (port 8080)
        └── api.swingscanner.app    → docker container "api" (port 8000)
                │
                ▼
        docker compose stack in /opt/swingtrade:
          frontend (nginx serving the built React app,
                    proxies its own /api and /ws to the api container)
          api      (FastAPI)
          worker   (arq — runs the scan cycle every 60s)
          db       (PostgreSQL)
          redis    (cache + job queue + pub/sub for live alerts)
```

In practice the React app talks to `/api` and `/ws` on its own origin
(`swingscanner.app`) — nginx inside the `frontend` container forwards those
internally to the `api` container over the Docker network
([frontend/nginx.conf](frontend/nginx.conf)). The `api.swingscanner.app` Caddy
route exists for direct API/docs access but isn't what the website itself uses.

Secrets (`POLYGON_API_KEY`, `SECRET_KEY`, `ENCRYPTION_KEY`, etc.) live only in
`/opt/swingtrade/.env` **on the droplet** — never committed to git.

**Known gap:** `www.swingscanner.app` has no DNS record yet, so it 404s/fails
to resolve. Only the bare `swingscanner.app` domain currently works. Fixing
this just needs a `www` DNS record (or redirect rule) added wherever the
domain's DNS is managed — flagged here, not yet done.

## How to make an update

1. **Change code locally**, in this repo, and test it.
2. **Commit and push to GitHub:**
   ```bash
   git add -A && git commit -m "describe the change"
   git push origin main
   ```
3. **Deploy to the droplet** — pull the new code and rebuild the affected
   containers:
   ```bash
   ssh -i ~/.ssh/do_droplet root@157.245.89.255 \
     "cd /opt/swingtrade && git pull && docker compose up -d --build"
   ```
   Rebuilding everything (`--build` with no service names) is safest but
   slower; if you only touched the backend, `docker compose up -d --build api
   worker` is faster and skips rebuilding the frontend image.
4. **Verify:**
   ```bash
   curl -s https://swingscanner.app/api/v1/health
   ```
   Should return `{"status":"ok", ...}`. For anything more, check logs:
   ```bash
   ssh -i ~/.ssh/do_droplet root@157.245.89.255 \
     "cd /opt/swingtrade && docker compose logs --tail 50 api worker"
   ```

### Changing secrets / provider settings

`.env` isn't in git, so a new API key, a changed `DATA_PROVIDER`, etc. needs a
direct edit on the droplet, then a restart of the services that read it:

```bash
ssh -i ~/.ssh/do_droplet root@157.245.89.255
cd /opt/swingtrade
nano .env                                  # edit the value(s)
docker compose up -d --build api worker    # restart with the new values
```

### Database migrations

If a change adds/modifies a database model, add an Alembic migration in
`backend/alembic/`. The `api` container runs `alembic upgrade` automatically
on startup ([docker-compose.yml](docker-compose.yml)), so migrations apply the
moment the container restarts — no manual step needed on the droplet.

## Costs

- DigitalOcean droplet: ~$6/month (this is the only recurring cost right now).
- Cloudflare: free plan (DNS + TLS).
- Massive/Polygon market data: free tier (5 requests/min, end-of-day data).

## If this needs to scale beyond personal use

Don't re-architect by hand — the repo already has the config for it. See the
Phase 2 section of
[docs/plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md](docs/plans/2026-07-23-feat-phased-personal-to-public-hosting-plan.md):
point Render at the same repo (it reads [render.yaml](render.yaml)
unmodified), and either host the frontend on a static site host of your
choice or keep it on the droplet — the application code doesn't change
either way, only where it's hosted.
