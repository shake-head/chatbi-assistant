"""Redis-backed user rate limiting with an in-process development fallback."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections import defaultdict

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import AppException

logger = logging.getLogger(__name__)
_memory_windows: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
_memory_lock = threading.Lock()


async def check_rate_limit(
    *,
    user_id: int,
    settings: Settings,
    scope: str,
    limit: int,
) -> None:
    """Raise 429 when a user exceeds the configured fixed-window limit."""

    if not settings.rate_limit_enabled or settings.app_env == "test":
        return

    now = int(time.time())
    window = max(1, settings.rate_limit_window_seconds)
    bucket = now // window
    key = f"chatbi:ratelimit:{scope}:{user_id}:{bucket}"
    count = await _increment_redis(settings, key, window)
    if count is None:
        count = _increment_memory(key, bucket)

    if count > limit:
        retry_after = window - (now % window)
        raise AppException(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests; please try again later",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


async def _increment_redis(settings: Settings, key: str, window: int) -> int | None:
    client: Redis | None = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window + 1)
        return int(count)
    except Exception as exc:
        logger.debug("redis_rate_limit_unavailable error=%s", type(exc).__name__)
        return None
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


def _increment_memory(key: str, bucket: int) -> int:
    with _memory_lock:
        stored_bucket, count = _memory_windows[key]
        if stored_bucket != bucket:
            count = 0
        count += 1
        _memory_windows[key] = (bucket, count)
        if len(_memory_windows) > 10_000:
            for stale_key, (stale_bucket, _) in list(_memory_windows.items()):
                if stale_bucket != bucket:
                    _memory_windows.pop(stale_key, None)
        return count
