from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_opaque_token,
    extract_user_id_from_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResendVerificationEmailRequest,
    ResetPasswordRequest,
    SignUpRequest,
    TokenResponse,
    UserResponse,
)
from app.services.email_service import (
    send_password_reset_email,
    send_verification_email,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _utcnow()


async def _get_user_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    result = await db.execute(
        select(User).where(or_(User.email == identifier, User.user_name == identifier))
    )
    return result.scalar_one_or_none()


def _set_email_verification_token(user: User) -> str:
    verification_token = create_opaque_token(user.id)
    user.email_verification_token_hash = hash_token(verification_token)
    user.email_verification_token_expires_at = _utcnow() + timedelta(
        hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
    )
    return verification_token


def _token_response(user: User, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


def _set_refresh_token(user: User) -> str:
    refresh_token = create_opaque_token(user.id)
    user.refresh_token_hash = hash_token(refresh_token)
    user.refresh_token_expires_at = _utcnow() + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    return refresh_token


def _clear_refresh_token(user: User) -> None:
    user.refresh_token_hash = None
    user.refresh_token_expires_at = None


async def sign_up(payload: SignUpRequest, db: AsyncSession) -> MessageResponse:
    existing_user = await _get_user_by_identifier(db, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    username_result = await db.execute(
        select(User).where(User.user_name == payload.user_name)
    )
    if username_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already taken"
        )

    user = User(
        name=payload.name,
        user_name=payload.user_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_email_verified=False,
    )
    db.add(user)
    await db.flush()

    verification_token = _set_email_verification_token(user)

    try:
        await run_in_threadpool(
            send_verification_email,
            user.email,
            user.name,
            verification_token,
        )
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    return MessageResponse(
        message="Account created. Check your email to verify your account."
    )


async def resend_verification_email(
    payload: ResendVerificationEmailRequest,
    db: AsyncSession,
) -> MessageResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or user.is_email_verified:
        return MessageResponse(
            message="If an unverified account with that email exists, a verification email has been sent."
        )

    verification_token = _set_email_verification_token(user)

    try:
        await run_in_threadpool(
            send_verification_email,
            user.email,
            user.name,
            verification_token,
        )
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    return MessageResponse(
        message="If an unverified account with that email exists, a verification email has been sent."
    )


async def change_password(
    current_user: User,
    payload: ChangePasswordRequest,
    db: AsyncSession,
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )
    if payload.new_password != payload.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.password_reset_token_hash = None
    current_user.password_reset_token_expires_at = None
    _clear_refresh_token(current_user)
    await db.commit()

    return MessageResponse(message="Password changed successfully")


async def login(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    user = await _get_user_by_identifier(db, payload.identifier)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before logging in",
        )

    refresh_token = _set_refresh_token(user)
    await db.commit()
    await db.refresh(user)
    return _token_response(user, refresh_token)


async def sign_out(payload: LogoutRequest, db: AsyncSession) -> MessageResponse:
    try:
        user_id = extract_user_id_from_opaque_token(payload.refresh_token)
    except HTTPException:
        return MessageResponse(message="Signed out successfully")

    user = await db.get(User, user_id)
    if user:
        _clear_refresh_token(user)
        await db.commit()

    return MessageResponse(message="Signed out successfully")


async def verify_email(token: str, db: AsyncSession) -> MessageResponse:
    user_id = extract_user_id_from_opaque_token(token)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.is_email_verified:
        return MessageResponse(message="Email is already verified")

    if user.email_verification_token_hash != hash_token(token) or _is_expired(
        user.email_verification_token_expires_at
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    user.is_email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_token_expires_at = None
    await db.commit()
    return MessageResponse(message="Email verified successfully")


async def forgot_password(
    payload: ForgotPasswordRequest, db: AsyncSession
) -> MessageResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user:
        return MessageResponse(
            message="If an account with that email exists, a password reset email has been sent."
        )

    reset_token = create_opaque_token(user.id)
    user.password_reset_token_hash = hash_token(reset_token)
    user.password_reset_token_expires_at = _utcnow() + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )

    try:
        await run_in_threadpool(
            send_password_reset_email, user.email, user.name, reset_token
        )
    except Exception:
        await db.rollback()
        raise

    await db.commit()

    return MessageResponse(
        message="If an account with that email exists, a password reset email has been sent."
    )


async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession
) -> MessageResponse:
    user_id = extract_user_id_from_opaque_token(payload.token)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.password_reset_token_hash != hash_token(payload.token) or _is_expired(
        user.password_reset_token_expires_at
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user.hashed_password = hash_password(payload.new_password)
    user.password_reset_token_hash = None
    user.password_reset_token_expires_at = None
    _clear_refresh_token(user)
    await db.commit()

    return MessageResponse(message="Password reset successfully")


async def refresh_token(
    payload: RefreshTokenRequest, db: AsyncSession
) -> TokenResponse:
    user_id = extract_user_id_from_opaque_token(payload.refresh_token)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if _is_expired(user.refresh_token_expires_at):
        _clear_refresh_token(user)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    if user.refresh_token_hash != hash_token(payload.refresh_token):
        _clear_refresh_token(user)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid",
        )

    refresh_token = _set_refresh_token(user)
    await db.commit()
    await db.refresh(user)
    return _token_response(user, refresh_token)
