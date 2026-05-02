import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, EmailStr

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]+$")


class MessageResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Operation completed successfully"}}
    )

    message: str


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "ali ahmed",
                "user_name": "ali_ahmed",
                "email": "ali@example.com",
                "is_email_verified": True,
            }
        },
    )

    id: int
    name: str
    user_name: str
    email: EmailStr
    is_email_verified: bool


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
                "refresh_token": "1.refresh-token-example-value",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "name": "ali ahmed",
                    "user_name": "ali_ahmed",
                    "email": "ali@example.com",
                    "is_email_verified": True,
                },
            }
        }
    )

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class SignUpRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "ali ahmed",
                "user_name": "ali_ahmed",
                "email": "ali@example.com",
                "password": "secret123",
            }
        }
    )

    name: str = Field(min_length=2, max_length=255)
    user_name: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("user_name")
    @classmethod
    def validate_user_name(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Username can contain lowercase letters, numbers, dots, underscores, and hyphens only"
            )
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "identifier": "ali@example.com",
                "password": "secret123",
            }
        }
    )

    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Email or username is required")
        return value


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"refresh_token": "1.refresh-token-example-value"}
        }
    )

    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"refresh_token": "1.refresh-token-example-value"}
        }
    )

    refresh_token: str = Field(min_length=10)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "ali@example.com"}}
    )

    email: EmailStr


class ResendVerificationEmailRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "ali@example.com"}}
    )

    email: EmailStr


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "secret123",
                "new_password": "newsecret123",
                "new_password_confirm": "newsecret123",
            }
        }
    )

    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=8, max_length=128)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "token": "1.reset-token-example-value",
                "new_password": "newsecret123",
            }
        }
    )

    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)
