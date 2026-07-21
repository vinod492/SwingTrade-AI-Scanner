# Putting SwingTrade on the internet (Netlify + Render)

The app has two halves:

1. **The website** (what you see and click) → hosted on **Netlify**. Free.
2. **The engine** (API server + scanner robot + database + Redis) → hosted on
   **Render**, because it has to run 24/7 and Netlify can't do that.
   Roughly $14/month on starter plans (two always-on services).

Total hands-on time: about 20 minutes, all clicking — the config files in this
repo do the heavy lifting.

## Step 0 — put the code on GitHub (one time)

Create an empty repository on github.com, then from the project folder:

```bash
cd ~/Documents/swingtrade-ai-scanner
git remote add origin https://github.com/YOUR-USERNAME/swingtrade-ai-scanner.git
git push -u origin main
```

Your `.env` (with your Massive key) is gitignored and will NOT be uploaded —
that's intentional. Keys are pasted into the hosting dashboards instead.

## Step 1 — deploy the engine on Render (~10 min)

1. Go to https://render.com → sign up / sign in with GitHub.
2. Click **New → Blueprint** and pick your `swingtrade-ai-scanner` repo.
3. Render reads [render.yaml](render.yaml) and offers to create: the API, the
   worker, a PostgreSQL database and a Redis instance. Approve it.
4. It will ask for the two secrets marked "paste":
   - `POLYGON_API_KEY` — your Massive key (rotate it first in the Massive
     dashboard if you haven't since it was shared in chat)
   - `ENCRYPTION_KEY` — run this locally and paste the output:
     `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
5. Deploy. When it's green, copy the API's public URL — it looks like
   `https://swingtrade-api.onrender.com`. Check it works:
   open `https://swingtrade-api.onrender.com/api/v1/health`.

No keys at all? Set `DATA_PROVIDER` to `sample` in the Render dashboard and the
engine runs on synthetic demo data.

## Step 2 — deploy the website on Netlify (~5 min)

1. First, in [netlify.toml](netlify.toml) (repo root), replace
   `YOUR-BACKEND-URL` with the Render URL from step 1, then:
   `git add netlify.toml && git commit -m "point netlify at backend" && git push`
2. Go to https://netlify.com → sign up / sign in with GitHub.
3. **Add new site → Import an existing project** → pick the repo.
   Build settings are auto-detected from `netlify.toml` — accept them.
4. Before the first deploy, add one environment variable
   (Site settings → Environment variables):
   - `VITE_WS_URL` = `wss://swingtrade-api.onrender.com/ws`
     (your Render URL with `wss://` in front and `/ws` at the end —
     live-update pushes connect straight to the engine because Netlify's
     proxy can't carry websockets)
5. Deploy. Your site is live at `https://something.netlify.app` —
   rename it or attach a custom domain in Netlify's settings.

## How it fits together

```
you → https://yoursite.netlify.app        (Netlify: the React app)
        ├── /api/* proxied to Render      (scanner data, auth, backtests)
        └── wss://…onrender.com/ws        (live prices & alert toasts)
Render: FastAPI api + arq worker + PostgreSQL + Redis (the 24/7 engine)
```

## Costs & alternatives

- **Render**: API + worker on `starter` ≈ $7 each/month; Postgres basic ≈ $6;
  Redis free tier. You can drop the API to the free plan, but it sleeps after
  idle periods (first request takes ~1 min to wake); the worker has no free tier.
- **Railway.app**: same architecture works there (~$5/month usage-based);
  create four services from the repo by hand — API (`backend/Dockerfile`),
  worker (same image, command `arq app.workers.worker.WorkerSettings`),
  plus their Postgres and Redis plugins.
- **Any VPS with Docker**: `docker compose up -d` runs everything on one box —
  cheapest at ~$5/month, but you manage it yourself.

## Updating the live site

Just push to `main` — Netlify and Render both redeploy automatically.
