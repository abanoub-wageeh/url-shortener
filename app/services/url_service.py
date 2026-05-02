from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base62 import encode_base62
from app.core.config import settings
from app.models.url import Url
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.url import CreateUrlRequest, UrlListResponse, UrlResponse


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


async def delete_url(
    url_id: int,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
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

    url.is_active = False
    url.deleted_at = _utcnow()
    await db.commit()

    return MessageResponse(message="URL deleted successfully")


async def update_url_status(
    url_id: int,
    is_active: bool,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
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

    url.is_active = is_active
    await db.commit()

    state = "activated" if is_active else "disabled"
    return MessageResponse(message=f"URL {state} successfully")


async def resolve_url(short_code: str, db: AsyncSession) -> str:
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

    await _increment_click_count(url.id, db)
    return url.original_url


async def _increment_click_count(url_id: int, db: AsyncSession) -> None:
    await db.execute(
        update(Url).where(Url.id == url_id).values(click_count=Url.click_count + 1)
    )
    await db.commit()
