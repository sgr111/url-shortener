from datetime import datetime

from pydantic import BaseModel, HttpUrl, field_validator


class URLCreate(BaseModel):
    original_url: HttpUrl
    expires_at: datetime | None = None
    max_clicks: int | None = None

    @field_validator("max_clicks")
    @classmethod
    def max_clicks_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("max_clicks must be a positive integer")
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
    created_at: datetime

    model_config = {"from_attributes": True}


class URLListOut(BaseModel):
    items: list[URLOut]
    total: int
    skip: int
    limit: int
    has_more: bool
