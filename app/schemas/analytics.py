from datetime import datetime

from pydantic import BaseModel


class ClickEventOut(BaseModel):
    id: int
    clicked_at: datetime
    ip_address: str | None
    user_agent: str | None
    country: str | None

    model_config = {"from_attributes": True}


class CountryCount(BaseModel):
    country: str | None
    count: int


class AnalyticsOut(BaseModel):
    url_id: int
    short_code: str
    original_url: str
    total_clicks: int
    max_clicks: int | None
    expires_at: datetime | None
    is_active: bool
    recent_clicks: list[ClickEventOut]
    top_countries: list[CountryCount]
