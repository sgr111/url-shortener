"""
Thin wrapper around Upstash Redis's REST API.

Why REST and not a normal Redis client: Upstash's REST API needs no
persistent TCP connection. Render's free tier sleeps the app on
inactivity — a normal Redis client's connection would need to be
re-established (and can hang/fail) on every wake-up. A plain HTTPS POST
has no such state to lose.

Fail-open design: if UPSTASH_REDIS_REST_URL/TOKEN aren't configured, or
any request errors out (timeout, Upstash outage, bad response), every
function here quietly no-ops / returns None. Caching is a performance
optimization — it must never be the reason a redirect breaks.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("cache")


def _is_enabled() -> bool:
    return bool(settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN)

async def _upstash_command(*args: Any) -> Any:
    """
    Sends a single Redis command via Upstash's REST API, e.g.
    _upstash_command("SET", "key", "value", "EX", "3600")
    Docs: https://upstash.com/docs/redis/features/restapi
    """
    if not _is_enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                settings.UPSTASH_REDIS_REST_URL,
                headers={"Authorization": f"Bearer {settings.UPSTASH_REDIS_REST_TOKEN}"},
                json=list(args),
            )
            resp.raise_for_status()
            return resp.json().get("result")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Cache command failed, falling back to DB: %s", exc)
        return None



async def cache_get(key: str) -> str | None:
    return await _upstash_command("GET", key)


async def cache_set(key: str, value: str, ttl_seconds: int | None = None) -> None:
    ttl = ttl_seconds if ttl_seconds is not None else settings.CACHE_TTL_SECONDS
    await _upstash_command("SET", key, value, "EX", str(ttl))


async def cache_delete(key: str) -> None:
    await _upstash_command("DEL", key)