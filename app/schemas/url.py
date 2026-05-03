import re
from datetime import datetime, timezone

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


CUSTOM_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RESERVED_ALIASES = {"api", "docs", "redoc", "openapi.json"}


def _validate_custom_alias(value: str | None) -> str | None:
    if value is None:
        return value

    value = value.strip()
    if value.lower() in RESERVED_ALIASES:
        raise ValueError("Custom alias is reserved")
    if not CUSTOM_ALIAS_PATTERN.fullmatch(value):
        raise ValueError(
            "Custom alias can contain letters, numbers, underscores, and hyphens only"
        )

    return value


def _validate_expires_at(value: datetime | None) -> datetime | None:
    if value is None:
        return value

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    if value <= datetime.now(timezone.utc):
        raise ValueError("Expiration date must be in the future")

    return value


class CreateUrlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "original_url": "https://example.com/page",
                "custom_alias": "my-link",
                "expires_at": "2026-06-01T00:00:00Z",
            }
        }
    )

    original_url: AnyHttpUrl = Field(max_length=2048)
    custom_alias: str | None = Field(default=None, min_length=3, max_length=64)
    expires_at: datetime | None = None

    @field_validator("custom_alias", mode="before")
    @classmethod
    def validate_custom_alias(cls, value: str | None) -> str | None:
        return _validate_custom_alias(value)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        return _validate_expires_at(value)


class UpdateUrlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "original_url": "https://example.com/updated-page",
                "custom_alias": "updated-link",
                "expires_at": "2026-06-01T00:00:00Z",
            }
        }
    )

    original_url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    custom_alias: str | None = Field(default=None, min_length=3, max_length=64)
    expires_at: datetime | None = None

    @field_validator("custom_alias", mode="before")
    @classmethod
    def validate_custom_alias(cls, value: str | None) -> str | None:
        return _validate_custom_alias(value)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        return _validate_expires_at(value)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "UpdateUrlRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "original_url" in self.model_fields_set and self.original_url is None:
            raise ValueError("Original URL cannot be null")
        if "custom_alias" in self.model_fields_set and self.custom_alias is None:
            raise ValueError("Custom alias cannot be null")
        return self


class UpdateUrlStatusRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"is_active": False}})

    is_active: bool


class UrlResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "original_url": "https://example.com/page",
                "short_code": "1",
                "short_url": "http://localhost:8000/1",
                "click_count": 0,
                "is_active": True,
                "expires_at": "2026-06-01T00:00:00Z",
                "created_at": "2026-05-02T19:30:00Z",
                "updated_at": "2026-05-02T19:30:00Z",
            }
        }
    )

    id: int
    original_url: str
    short_code: str
    short_url: str
    click_count: int
    is_active: bool
    expires_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class UrlListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 0,
                "page": 1,
                "limit": 20,
                "pages": 0,
            }
        }
    )

    items: list[UrlResponse]
    total: int
    page: int
    limit: int
    pages: int
