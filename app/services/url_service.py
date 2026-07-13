"""
URL service — all business logic lives here, endpoints stay thin.

Key design decisions:
  - get_url_by_code() is the single choke point for redirect lookup.
    When Redis is added in future, cache invalidation happens here only.
  - click_count is incremented atomically in the DB (not read-modify-write)
    to avoid race conditions under concurrent traffic.
  - Expiry check order: is_active → expires_at → max_clicks
    Short-circuits on the cheapest check first.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base62 import encode
from app.core.config import settings
from app.models.url import URL, ClickEvent, WebhookQueue
from app.schemas.analytics import AnalyticsOut, ClickEventOut, CountryCount
from app.schemas.url import URLCreate, URLListOut, URLOut


def _build_short_url(short_code: str) -> str:
    return f"{settings.BASE_URL}/{short_code}"


def _to_url_out(url: URL) -> URLOut:
    return URLOut(
        id=url.id,
        original_url=str(url.original_url),
        short_code=url.short_code,
        short_url=_build_short_url(url.short_code),
        click_count=url.click_count,
        is_active=url.is_active,
        expires_at=url.expires_at,
        max_clicks=url.max_clicks,
        webhook_url=url.webhook_url,
        created_at=url.created_at,
    )


async def create_short_url(
    db: AsyncSession,
    data: URLCreate,
    user_id: int | None = None,
) -> URLOut:
    # Insert with a temporary unique short_code first
    import uuid
    temp_code = str(uuid.uuid4().int)[:10]  # 10 digit temp, always fits VARCHAR(10)

    url = URL(
        original_url=str(data.original_url),
        short_code=temp_code,
        user_id=user_id,
        expires_at=data.expires_at,
        max_clicks=data.max_clicks,
        webhook_url=str(data.webhook_url) if data.webhook_url else None,
    )
    db.add(url)
    await db.flush()  # Gets url.id without committing

    # Now encode the real ID to Base62 and update
    url.short_code = encode(url.id)
    await db.commit()
    await db.refresh(url)
    return _to_url_out(url)


async def get_url_by_code(db: AsyncSession, short_code: str) -> URL | None:
    """
    Single lookup point for redirects.
    Future: add Redis cache check here before hitting DB.
    Indexed on short_code — O(log n) lookup.
    """
    result = await db.execute(select(URL).where(URL.short_code == short_code))
    return result.scalar_one_or_none()


def check_url_validity(url: URL) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Checks in order: active → expiry date → click limit.
    """
    if not url.is_active:
        return False, "URL has been deactivated"

    now = datetime.now(timezone.utc)
    if url.expires_at:
        # SQLite returns naive datetimes; PostgreSQL returns aware. Handle both.
        expires = url.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            return False, "URL has expired"

    if url.max_clicks is not None and url.click_count >= url.max_clicks:
        return False, "URL has reached its maximum click limit"

    return True, ""


async def increment_click_count(db: AsyncSession, url_id: int) -> None:
    """Atomic increment — avoids read-modify-write race condition."""
    await db.execute(
        update(URL).where(URL.id == url_id).values(click_count=URL.click_count + 1)
    )
    await db.commit()


async def log_click_event(
    db: AsyncSession,
    url_id: int,
    ip_address: str | None,
    user_agent: str | None,
    country: str | None = None,
) -> None:
    """Called as a BackgroundTask — runs after redirect response is sent."""
    event = ClickEvent(
        url_id=url_id,
        ip_address=ip_address,
        user_agent=user_agent,
        country=country,
    )
    db.add(event)
    await db.commit()


async def enqueue_webhook_job(
    db: AsyncSession,
    url_id: int,
    webhook_url: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """
    Insert a pending WebhookQueue row for this click.

    Delivery itself happens in the APScheduler processor (core/scheduler.py),
    not here — this function only records intent to notify. This is what
    makes webhook-on-click retry-safe: if delivery fails, the row stays
    'pending'/gets rescheduled instead of the event being lost like it
    would be with a plain fire-and-forget BackgroundTask.
    """
    job = WebhookQueue(
        url_id=url_id,
        webhook_url=webhook_url,
        payload={
            "url_id": url_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(job)
    await db.commit()


async def get_analytics(db: AsyncSession, url_id: int, user_id: int) -> AnalyticsOut | None:
    result = await db.execute(
        select(URL).where(URL.id == url_id, URL.user_id == user_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        return None

    # Last 10 clicks
    clicks_result = await db.execute(
        select(ClickEvent)
        .where(ClickEvent.url_id == url_id)
        .order_by(ClickEvent.clicked_at.desc())
        .limit(10)
    )
    recent_clicks = clicks_result.scalars().all()

    # Top countries by click count
    country_result = await db.execute(
        select(ClickEvent.country, func.count(ClickEvent.id).label("count"))
        .where(ClickEvent.url_id == url_id)
        .group_by(ClickEvent.country)
        .order_by(func.count(ClickEvent.id).desc())
        .limit(5)
    )
    top_countries = [
        CountryCount(country=row.country, count=row.count)
        for row in country_result.all()
    ]

    return AnalyticsOut(
        url_id=url.id,
        short_code=url.short_code,
        original_url=str(url.original_url),
        total_clicks=url.click_count,
        max_clicks=url.max_clicks,
        expires_at=url.expires_at,
        is_active=url.is_active,
        recent_clicks=[ClickEventOut.model_validate(c) for c in recent_clicks],
        top_countries=top_countries,
    )


async def list_urls(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 10,
) -> URLListOut:
    MAX_PAGE_SIZE = 50
    limit = min(limit, MAX_PAGE_SIZE)  # Silently clamp — same pattern as v4

    count_result = await db.execute(
        select(func.count(URL.id)).where(URL.user_id == user_id, URL.is_active == True)  # noqa: E712
    )
    total = count_result.scalar_one()

    urls_result = await db.execute(
        select(URL)
        .where(URL.user_id == user_id, URL.is_active == True)  # noqa: E712
        .order_by(URL.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    urls = urls_result.scalars().all()

    return URLListOut(
        items=[_to_url_out(u) for u in urls],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


async def deactivate_url(db: AsyncSession, url_id: int, user_id: int) -> bool:
    """Soft delete — sets is_active=False. Data + analytics preserved."""
    result = await db.execute(
        select(URL).where(URL.id == url_id, URL.user_id == user_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        return False
    url.is_active = False
    await db.commit()
    return True