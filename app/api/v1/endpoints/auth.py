from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_db
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
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def sign_up(
    payload: SignUpRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    return await auth_service.sign_up(payload, db)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    return await auth_service.login(payload, db)


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await auth_service.change_password(current_user, payload, db)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    return await auth_service.sign_out(payload, db)


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(
    token: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await auth_service.verify_email(token, db)


@router.post("/resend-verification-email", response_model=MessageResponse)
async def resend_verification_email(
    payload: ResendVerificationEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await auth_service.resend_verification_email(payload, db)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await auth_service.forgot_password(payload, db)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await auth_service.reset_password(payload, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await auth_service.refresh_token(payload, db)
