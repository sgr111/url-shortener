from datetime import datetime

from pydantic import BaseModel, HttpUrl, field_validator


class URLCreate(BaseModel):
    original_url: HttpUrl
    expires_at: datetime | None = None
    max_clicks: int | None = None
    webhook_url: HttpUrl | None = None  # optional — notified via retry-queue on each click
    password: str | None = None  # optional — required as ?password= to redirect

    @field_validator("max_clicks")
    @classmethod
    def max_clicks_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("max_clicks must be a positive integer")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 4:
            raise ValueError("password must be at least 4 characters")
        return v


class URLOut(BaseModel):
    id: int
    original_url: str
    short_code: str
    short_url: str
    click_count: int
    is_active: bool
    expires_at: datetime | None
    max_clicks: int | None
    webhook_url: str | None
    is_password_protected: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class URLListOut(BaseModel):
    items: list[URLOut]
    total: int
    skip: int
    limit: int
    has_more: bool


class BulkURLRow(BaseModel):
    """One row's outcome from a bulk CSV shorten request."""
    row: int
    original_url: str
    success: bool
    short_url: str | None = None
    error: str | None = None


class BulkURLResult(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[BulkURLRow]