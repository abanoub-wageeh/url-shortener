from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import url_service

router = APIRouter(tags=["redirects"])


@router.get("/{short_code}", status_code=status.HTTP_302_FOUND)
async def redirect_to_original_url(
    short_code: str = Path(..., min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    original_url = await url_service.resolve_url(short_code, db)
    return RedirectResponse(original_url, status_code=status.HTTP_302_FOUND)
