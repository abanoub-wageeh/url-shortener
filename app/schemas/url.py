from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class CreateUrlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"original_url": "https://example.com/page"}}
    )

    original_url: AnyHttpUrl = Field(max_length=2048)


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
