from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core.security import hash_password, hash_token
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, RefreshTokenRequest
from app.services import auth_service


def build_user(**overrides) -> User:
    data = {
        "id": 1,
        "name": "Test User",
        "user_name": "test_user",
        "email": "user@example.com",
        "hashed_password": hash_password("secret123"),
        "is_email_verified": True,
    }
    data.update(overrides)
    return User(**data)


@pytest.mark.asyncio
async def test_change_password_rejects_incorrect_current_password():
    user = build_user()
    db = AsyncMock()
    payload = ChangePasswordRequest(
        current_password="wrongpass123",
        new_password="newsecret123",
        new_password_confirm="newsecret123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.change_password(user, payload, db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Current password is incorrect"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_email_rejects_mismatched_token():
    token = "1.valid-token-value"
    user = build_user(
        is_email_verified=False,
        email_verification_token_hash=hash_token("1.other-token-value"),
        email_verification_token_expires_at=auth_service._utcnow() + timedelta(hours=1),
    )
    db = AsyncMock()
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.verify_email(token, db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid or expired verification token"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_token_clears_invalid_token_hash():
    token = "1.refresh-token-value"
    user = build_user(
        refresh_token_hash=hash_token("1.some-other-token"),
        refresh_token_expires_at=auth_service._utcnow() + timedelta(days=1),
    )
    db = AsyncMock()
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.refresh_token(RefreshTokenRequest(refresh_token=token), db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Refresh token is invalid"
    assert user.refresh_token_hash is None
    assert user.refresh_token_expires_at is None
    db.commit.assert_awaited_once()
