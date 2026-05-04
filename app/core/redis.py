from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import settings

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - redis is optional until installed.
    Redis = None  # type: ignore[assignment]


RedisClient = Any

_redis_client: RedisClient | None = None


def _get_redis_client() -> RedisClient | None:
    global _redis_client

    if not settings.REDIRECT_CACHE_ENABLED or Redis is None:
        return None

    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def get_redis() -> AsyncGenerator[RedisClient | None, None]:
    yield _get_redis_client()
