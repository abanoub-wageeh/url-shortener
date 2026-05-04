import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.core.redis import RedisClient


@dataclass(frozen=True)
class CachedRedirect:
    url_id: int
    original_url: str
    expires_at: datetime | None


def _cache_key(short_code: str) -> str:
    return f"redirect:{short_code}"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _ttl_seconds(expires_at: datetime | None) -> int:
    ttl = settings.REDIRECT_CACHE_TTL_SECONDS
    expires_at = _as_utc(expires_at)
    if expires_at is None:
        return ttl

    seconds_until_expiration = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    return min(ttl, seconds_until_expiration)


async def get_link(short_code: str, redis: RedisClient) -> CachedRedirect | None:
    cached = await redis.get(_cache_key(short_code))
    if cached is None:
        return None

    data = json.loads(cached)
    expires_at = data.get("expires_at")
    return CachedRedirect(
        url_id=int(data["url_id"]),
        original_url=data["original_url"],
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
    )


async def set_link(
    short_code: str,
    url_id: int,
    original_url: str,
    expires_at: datetime | None,
    redis: RedisClient,
) -> None:
    ttl = _ttl_seconds(expires_at)
    if ttl <= 0:
        return

    expires_at = _as_utc(expires_at)
    value = json.dumps(
        {
            "url_id": url_id,
            "original_url": original_url,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    )
    await redis.setex(_cache_key(short_code), ttl, value)


async def delete_link(short_code: str, redis: RedisClient) -> None:
    await redis.delete(_cache_key(short_code))
