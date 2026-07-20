"""WebSocket fan-out: one Redis pub/sub listener per API process broadcasts
worker events (score updates, alerts, snapshots) to all connected clients."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.services.cache import EVENTS_CHANNEL, get_redis

log = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._listener: asyncio.Task | None = None

    async def start(self) -> None:
        if self._listener is None:
            self._listener = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
            self._listener = None

    async def _listen(self) -> None:
        while True:
            r = await get_redis()
            if r is None:
                await asyncio.sleep(10)
                from app.services import cache
                cache.reset_redis()  # retry connection periodically
                continue
            try:
                pubsub = r.pubsub()
                await pubsub.subscribe(EVENTS_CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") == "message":
                        await self.broadcast(message["data"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("ws listener dropped (%s), retrying", exc)
                await asyncio.sleep(5)

    async def broadcast(self, raw: str) -> None:
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def handle(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        try:
            while True:
                await ws.receive_text()  # client pings; content ignored
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(ws)


hub = WebSocketHub()
