"""Thin Redis layer with graceful degradation: if Redis is unreachable the app
keeps working from the database (hot caches and live pushes just turn off)."""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

log = logging.getLogger(__name__)

EVENTS_CHANNEL = "swingtrade:events"
SCANNER_KEY = "swingtrade:scanner:latest"

_client: Redis | None = None
_known_bad = False


async def get_redis() -> Redis | None:
    global _client, _known_bad
    if _client is not None:
        return _client
    if _known_bad:
        return None
    try:
        client = Redis.from_url(get_settings().redis_url, decode_responses=True,
                                socket_connect_timeout=2)
        await client.ping()
        _client = client
        return client
    except Exception as exc:
        log.warning("redis unavailable (%s) — running without cache/live push", exc)
        _known_bad = True
        return None


def reset_redis() -> None:
    global _client, _known_bad
    _client = None
    _known_bad = False


async def cache_set_json(key: str, value: Any, ttl: int | None = None) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        log.warning("redis set failed: %s", exc)


async def cache_get_json(key: str) -> Any | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("redis get failed: %s", exc)
        return None


async def publish_event(event_type: str, payload: Any) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.publish(EVENTS_CHANNEL, json.dumps({"type": event_type, "payload": payload},
                                                   default=str))
    except Exception as exc:
        log.warning("redis publish failed: %s", exc)
