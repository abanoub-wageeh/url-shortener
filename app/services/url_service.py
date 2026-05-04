from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base62 import encode_base62
from app.core.config import settings
from app.core.redis import RedisClient
from app.models.url import Url
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.url import CreateUrlRequest, UpdateUrlRequest, UrlListResponse, UrlResponse
from app.services import redirect_cache_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _short_url(short_code: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{short_code}"


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _utcnow()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _url_response(url: Url) -> UrlResponse:
    return UrlResponse(
        id=url.id,
        original_url=url.original_url,
        short_code=url.short_code,
        short_url=_short_url(url.short_code),
        click_count=url.click_count,
        is_active=url.is_active,
        expires_at=_as_utc(url.expires_at),
        created_at=_as_utc(url.created_at),
        updated_at=_as_utc(url.updated_at),
    )


async def _get_owned_url(url_id: int, current_user: User, db: AsyncSession) -> Url:
    result = await db.execute(
        select(Url).where(
            Url.id == url_id,
            Url.user_id == current_user.id,
            Url.deleted_at.is_(None),
        )
    )
    url = result.scalar_one_or_none()
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="URL not found")
    return url


async def _delete_cached_short_codes(
    short_codes: set[str | None],
    redis: RedisClient | None,
) -> None:
    if redis is None:
        return

    for short_code in short_codes:
        if short_code is None:
            continue
        try:
            await redirect_cache_service.delete_link(short_code, redis)
        except Exception:
            pass


async def create_url(
    payload: CreateUrlRequest,
    current_user: User,
    db: AsyncSession,
) -> UrlResponse:
    url = Url(
        user_id=current_user.id,
        original_url=str(payload.original_url),
        expires_at=payload.expires_at,
    )
    db.add(url)
    await db.flush()

    url.short_code = payload.custom_alias or encode_base62(url.id)

    try:
        await db.commit()
        await db.refresh(url)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Short code already exists",
        ) from exc

    return _url_response(url)


async def list_urls(
    current_user: User,
    page: int,
    limit: int,
    db: AsyncSession,
) -> UrlListResponse:
    offset = (page - 1) * limit
    filters = (Url.user_id == current_user.id, Url.deleted_at.is_(None))

    total_result = await db.execute(select(func.count()).select_from(Url).where(*filters))
    total = total_result.scalar_one()

    result = await db.execute(
        select(Url)
        .where(*filters)
        .order_by(Url.id.desc())
        .offset(offset)
        .limit(limit)
    )
    urls = result.scalars().all()
    pages = (total + limit - 1) // limit if total else 0

    return UrlListResponse(
        items=[_url_response(url) for url in urls],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


async def get_url(
    url_id: int,
    current_user: User,
    db: AsyncSession,
) -> UrlResponse:
    url = await _get_owned_url(url_id, current_user, db)
    return _url_response(url)


async def update_url(
    url_id: int,
    payload: UpdateUrlRequest,
    current_user: User,
    db: AsyncSession,
    redis: RedisClient | None = None,
) -> UrlResponse:
    url = await _get_owned_url(url_id, current_user, db)
    short_codes_to_invalidate = {url.short_code}
    if "custom_alias" in payload.model_fields_set:
        short_codes_to_invalidate.add(payload.custom_alias)

    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    if "original_url" in payload.model_fields_set:
        url.original_url = str(payload.original_url)
    if "custom_alias" in payload.model_fields_set:
        url.short_code = payload.custom_alias
    if "expires_at" in payload.model_fields_set:
        url.expires_at = payload.expires_at

    try:
        await db.commit()
        await db.refresh(url)
    except IntegrityError as exc:
        await db.rollback()
        await _delete_cached_short_codes(short_codes_to_invalidate, redis)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Short code already exists",
        ) from exc

    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    return _url_response(url)


async def delete_url(
    url_id: int,
    current_user: User,
    db: AsyncSession,
    redis: RedisClient | None = None,
) -> MessageResponse:
    url = await _get_owned_url(url_id, current_user, db)
    short_codes_to_invalidate = {url.short_code}
    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    url.is_active = False
    url.deleted_at = _utcnow()
    await db.commit()
    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    return MessageResponse(message="URL deleted successfully")


async def update_url_status(
    url_id: int,
    is_active: bool,
    current_user: User,
    db: AsyncSession,
    redis: RedisClient | None = None,
) -> MessageResponse:
    url = await _get_owned_url(url_id, current_user, db)
    short_codes_to_invalidate = {url.short_code}
    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    url.is_active = is_active
    await db.commit()
    await _delete_cached_short_codes(short_codes_to_invalidate, redis)

    state = "activated" if is_active else "disabled"
    return MessageResponse(message=f"URL {state} successfully")


async def resolve_url(
    short_code: str,
    db: AsyncSession,
    redis: RedisClient | None = None,
) -> str:
    cached = None
    if redis is not None:
        try:
            cached = await redirect_cache_service.get_link(short_code, redis)
        except Exception:
            cached = None

    if cached is not None and not _is_expired(cached.expires_at):
        await _increment_click_count(cached.url_id, db)
        return cached.original_url

    result = await db.execute(
        select(Url).where(
            Url.short_code == short_code,
            Url.deleted_at.is_(None),
            Url.is_active.is_(True),
        )
    )
    url = result.scalar_one_or_none()
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="URL not found")

    if _is_expired(url.expires_at):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="URL not found")

    if redis is not None:
        try:
            await redirect_cache_service.set_link(
                url.short_code,
                url.id,
                url.original_url,
                url.expires_at,
                redis,
            )
        except Exception:
            pass

    await _increment_click_count(url.id, db)
    return url.original_url


async def _increment_click_count(url_id: int, db: AsyncSession) -> None:
    await db.execute(
        update(Url).where(Url.id == url_id).values(click_count=Url.click_count + 1)
    )
    await db.commit()
