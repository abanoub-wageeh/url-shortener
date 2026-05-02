import re
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


CUSTOM_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RESERVED_ALIASES = {"api", "docs", "redoc", "openapi.json"}


class CreateUrlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "original_url": "https://example.com/page",
                "custom_alias": "my-link",
            }
        }
    )

    original_url: AnyHttpUrl = Field(max_length=2048)
    custom_alias: str | None = Field(default=None, min_length=3, max_length=64)

    @field_validator("custom_alias", mode="before")
    @classmethod
    def validate_custom_alias(cls, value: str | None) -> str | None:
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
