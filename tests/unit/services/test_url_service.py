from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.base62 import encode_base62
from app.core.security import hash_password
from app.models.url import Url
from app.models.user import User
from app.schemas.url import CreateUrlRequest
from app.services import url_service


async def create_user(db_session, email="user@example.com", user_name="test_user"):
    user = User(
        name="Test User",
        user_name=user_name,
        email=email,
        hashed_password=hash_password("secret123"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_short_url(
    db_session, user, original_url="https://example.com/page", custom_alias=None
):
    return await url_service.create_url(
        CreateUrlRequest(original_url=original_url, custom_alias=custom_alias),
        user,
        db_session,
    )


@pytest.mark.asyncio
async def test_create_url_generates_base62_short_code(db_session):
    user = await create_user(db_session)

    response = await create_short_url(db_session, user)

    assert response.short_code == encode_base62(response.id)
    assert response.short_url.endswith(f"/{response.short_code}")
    assert response.click_count == 0
    assert response.is_active is True


@pytest.mark.asyncio
async def test_create_url_uses_custom_alias_when_provided(db_session):
    user = await create_user(db_session)

    response = await create_short_url(db_session, user, custom_alias="my-alias_123")

    assert response.short_code == "my-alias_123"
    assert response.short_url.endswith("/my-alias_123")
    assert await url_service.resolve_url("my-alias_123", db_session) == response.original_url


@pytest.mark.asyncio
async def test_create_url_returns_409_for_duplicate_custom_alias(db_session):
    user = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    await create_short_url(db_session, user, custom_alias="taken-alias")

    with pytest.raises(HTTPException) as exc_info:
        await create_short_url(db_session, other_user, custom_alias="taken-alias")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Short code already exists"


@pytest.mark.asyncio
async def test_soft_deleted_custom_alias_still_returns_409_on_reuse(db_session):
    user = await create_user(db_session)
    created = await create_short_url(db_session, user, custom_alias="reserved-alias")
    await url_service.delete_url(created.id, user, db_session)

    with pytest.raises(HTTPException) as exc_info:
        await create_short_url(db_session, user, custom_alias="reserved-alias")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Short code already exists"


@pytest.mark.parametrize("custom_alias", ["api", "redoc", "bad alias", "bad.alias", "ab"])
def test_create_url_request_rejects_invalid_or_reserved_custom_alias(custom_alias):
    with pytest.raises(ValidationError):
        CreateUrlRequest(
            original_url="https://example.com/page",
            custom_alias=custom_alias,
        )


@pytest.mark.asyncio
async def test_list_urls_uses_page_pagination_and_excludes_deleted(db_session):
    user = await create_user(db_session)
    first = await create_short_url(db_session, user, "https://example.com/1")
    second = await create_short_url(db_session, user, "https://example.com/2")
    third = await create_short_url(db_session, user, "https://example.com/3")
    fourth = await create_short_url(db_session, user, "https://example.com/4")
    fifth = await create_short_url(db_session, user, "https://example.com/5")

    url = await db_session.get(Url, first.id)
    url.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    response = await url_service.list_urls(user, page=1, limit=2, db=db_session)

    assert response.total == 4
    assert response.page == 1
    assert response.limit == 2
    assert response.pages == 2
    assert [item.id for item in response.items] == [fifth.id, fourth.id]

    response = await url_service.list_urls(user, page=2, limit=2, db=db_session)
    assert [item.id for item in response.items] == [third.id, second.id]


@pytest.mark.asyncio
async def test_update_url_status_disables_and_activates_url(db_session):
    user = await create_user(db_session)
    created = await create_short_url(db_session, user)

    response = await url_service.update_url_status(created.id, False, user, db_session)

    assert response.message == "URL disabled successfully"
    url = await db_session.get(Url, created.id)
    assert url.is_active is False
    assert url.deleted_at is None

    list_response = await url_service.list_urls(user, page=1, limit=20, db=db_session)
    assert list_response.total == 1
    assert list_response.items[0].is_active is False

    with pytest.raises(HTTPException) as exc_info:
        await url_service.resolve_url(created.short_code, db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "URL not found"

    response = await url_service.update_url_status(created.id, True, user, db_session)

    assert response.message == "URL activated successfully"
    await db_session.refresh(url)
    assert url.is_active is True
    assert await url_service.resolve_url(created.short_code, db_session) == created.original_url


@pytest.mark.asyncio
async def test_delete_url_soft_deletes_and_hides_url(db_session):
    user = await create_user(db_session)
    created = await create_short_url(db_session, user)

    response = await url_service.delete_url(created.id, user, db_session)

    assert response.message == "URL deleted successfully"
    url = await db_session.get(Url, created.id)
    assert url.is_active is False
    assert url.deleted_at is not None

    list_response = await url_service.list_urls(user, page=1, limit=20, db=db_session)
    assert list_response.total == 0

    with pytest.raises(HTTPException) as exc_info:
        await url_service.delete_url(created.id, user, db_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_url_increments_click_count(db_session):
    user = await create_user(db_session)
    created = await create_short_url(db_session, user)

    assert await url_service.resolve_url(created.short_code, db_session) == created.original_url
    assert await url_service.resolve_url(created.short_code, db_session) == created.original_url

    url = await db_session.get(Url, created.id)
    await db_session.refresh(url)
    assert url.click_count == 2


@pytest.mark.asyncio
async def test_update_url_status_returns_404_for_another_users_url(db_session):
    owner = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    created = await create_short_url(db_session, owner)

    with pytest.raises(HTTPException) as exc_info:
        await url_service.update_url_status(created.id, False, other_user, db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "URL not found"


@pytest.mark.asyncio
async def test_update_url_status_returns_404_for_deleted_url(db_session):
    user = await create_user(db_session)
    created = await create_short_url(db_session, user)
    await url_service.delete_url(created.id, user, db_session)

    with pytest.raises(HTTPException) as exc_info:
        await url_service.update_url_status(created.id, True, user, db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "URL not found"
