from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.url import (
    CreateUrlRequest,
    UpdateUrlRequest,
    UpdateUrlStatusRequest,
    UrlListResponse,
    UrlResponse,
)
from app.services import url_service

router = APIRouter(prefix="/api/v1/urls", tags=["urls"])


@router.post("", response_model=UrlResponse, status_code=status.HTTP_201_CREATED)
async def create_url(
    payload: CreateUrlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlResponse:
    return await url_service.create_url(payload, current_user, db)


@router.get("", response_model=UrlListResponse)
async def list_urls(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlListResponse:
    return await url_service.list_urls(current_user, page, limit, db)


@router.get("/{url_id}", response_model=UrlResponse)
async def get_url(
    url_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlResponse:
    return await url_service.get_url(url_id, current_user, db)


@router.patch("/{url_id}", response_model=UrlResponse)
async def update_url(
    url_id: int,
    payload: UpdateUrlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlResponse:
    return await url_service.update_url(url_id, payload, current_user, db)


@router.delete("/{url_id}", response_model=MessageResponse)
async def delete_url(
    url_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await url_service.delete_url(url_id, current_user, db)


@router.patch("/{url_id}/status", response_model=MessageResponse)
async def update_url_status(
    url_id: int,
    payload: UpdateUrlStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await url_service.update_url_status(url_id, payload.is_active, current_user, db)
