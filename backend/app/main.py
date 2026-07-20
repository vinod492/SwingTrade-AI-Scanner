"""SwingTrade AI Scanner — FastAPI application.

API docs: /docs (Swagger) and /redoc. All routes live under /api/v1; live
updates stream over /ws.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, alerts, auth, backtests, ideas, scanner, symbols, user_settings, watchlist
from app.config import get_settings
from app.db.seed import bootstrap
from app.ws import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap()  # idempotent: creates missing tables, seeds the universe
    await hub.start()
    yield
    await hub.stop()


app = FastAPI(
    title="SwingTrade AI Scanner",
    version="1.0.0",
    description=(
        "Scans the US stock market and ranks swing-trade opportunities "
        "(2 days – 4 weeks) with a 0–100 Swing Score built from momentum, "
        "volatility, volume, breakout structure, options activity and catalysts. "
        "For research only — not financial advice."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
for router in (auth.router, scanner.router, symbols.router, ideas.router, ai.router,
               alerts.router, watchlist.router, backtests.router, user_settings.router):
    app.include_router(router, prefix=API)


@app.get("/api/v1/health", tags=["health"])
async def health():
    settings = get_settings()
    return {"status": "ok", "data_provider": settings.data_provider,
            "ai_provider": settings.ai_provider}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.handle(ws)
