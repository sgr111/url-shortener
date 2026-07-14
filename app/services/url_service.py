"""
URL service — all business logic lives here, endpoints stay thin.

Key design decisions:
  - get_url_by_code() is the single choke point for redirect lookup.
    Cache-aside pattern: Redis (Upstash) checked first, DB on miss.
  - click_count is incremented atomically in the DB (not read-modify-write)
    to avoid race conditions under concurrent traffic.
  - Expiry check order: is_active → expires_at → max_clicks
    Short-circuits on the cheapest check first.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base62 import encode
from app.core.cache import cache_delete, cache_get, cache_set
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.url import URL, ClickEvent, WebhookQueue
from app.schemas.analytics import AnalyticsOut, ClickEventOut, CountryCount
from app.schemas.url import BulkURLResult, BulkURLRow, URLCreate, URLListOut, URLOut


def _cache_key(short_code: str) -> str:
    return f"url:{short_code}"


@dataclass
class CachedURLRow:
    """
    A lightweight stand-in for a URL ORM row, reconstructed from cached
    JSON. Deliberately mirrors the ORM attribute names so downstream code
    (check_url_validity, check_password, redirect.py) works unchanged
    whether get_url_by_code() returned this or a real URL row.
    """
    id: int
    original_url: str
    short_code: str
    is_active: bool
    expires_at: datetime | None
    max_clicks: int | None
    click_count: int
    webhook_url: str | None
    password_hash: str | None


def _url_to_cache_json(url: URL) -> str:
    return json.dumps({
        "id": url.id,
        "original_url": str(url.original_url),
        "short_code": url.short_code,
        "is_active": url.is_active,
        "expires_at": url.expires_at.isoformat() if url.expires_at else None,
        "max_clicks": url.max_clicks,
        "click_count": url.click_count,
        "webhook_url": url.webhook_url,
        "password_hash": url.password_hash,
    })


def _cache_json_to_row(raw: str) -> CachedURLRow | None:
    try:
        data = json.loads(raw)
        return CachedURLRow(
            id=data["id"],
            original_url=data["original_url"],
            short_code=data["short_code"],
            is_active=data["is_active"],
            expires_at=datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None,
            max_clicks=data["max_clicks"],
            click_count=data["click_count"],
            webhook_url=data["webhook_url"],
            password_hash=data["password_hash"],
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None  # malformed cache entry — treat as a miss


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
        is_password_protected=url.password_hash is not None,
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
        password_hash=hash_password(data.password) if data.password else None,
    )
    db.add(url)
    await db.flush()  # Gets url.id without committing

    # Now encode the real ID to Base62 and update
    url.short_code = encode(url.id)
    await db.commit()
    await db.refresh(url)
    return _to_url_out(url)


async def get_url_by_code(db: AsyncSession, short_code: str) -> URL | CachedURLRow | None:
    """
    Single lookup point for redirects. Cache-aside pattern:
      1. Check Redis (Upstash) — return immediately on hit
      2. On miss, query Postgres, populate cache with a TTL, return

    Correctness note: click_count in the cache can go briefly stale between
    a click and the next lookup. increment_click_count() below refreshes
    the cache entry (with the new click_count) on every click rather than
    deleting it, so popular links stay cached instead of forcing a DB read
    on every single subsequent click.
    """
    key = _cache_key(short_code)
    cached_raw = await cache_get(key)
    if cached_raw:
        cached_row = _cache_json_to_row(cached_raw)
        if cached_row:
            return cached_row

    result = await db.execute(select(URL).where(URL.short_code == short_code))
    url = result.scalar_one_or_none()
    if url:
        await cache_set(key, _url_to_cache_json(url))
    return url


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


def check_password(url: URL, provided_password: str | None) -> bool:
    """Returns True if the URL has no password, or the provided one matches."""
    if not url.password_hash:
        return True
    if not provided_password:
        return False
    return verify_password(provided_password, url.password_hash)


async def increment_click_count(
    db: AsyncSession,
    url: URL | CachedURLRow,
    short_code: str | None = None,
) -> None:
    """
    Atomic increment — avoids read-modify-write race condition.

    If short_code is given, also *refreshes* (not deletes) that cache
    entry with the new click_count. An earlier version of this function
    deleted the cache entry instead — that looked safer for max_clicks
    correctness, but it meant every single click forced the *next*
    lookup back to a DB read, which defeats the entire point of caching
    on exactly the traffic pattern (popular, frequently-clicked links)
    where it matters most. Re-writing the entry keeps it warm while
    still keeping click_count accurate for the next validity check.
    """
    # Capture the pre-update count now — SQLAlchemy's synchronize_session
    # ('evaluate' strategy, the default) auto-updates this same in-memory
    # `url` object's click_count as a side effect of the UPDATE below if
    # it's a tracked ORM instance. Reading url.click_count *after* the
    # execute() would then double-count it (seen live: click_count came
    # back as 2 after a single click).
    previous_click_count = url.click_count

    await db.execute(
        update(URL).where(URL.id == url.id).values(click_count=URL.click_count + 1)
    )
    await db.commit()
    if short_code:
        refreshed = json.dumps({
            "id": url.id,
            "original_url": str(url.original_url),
            "short_code": short_code,
            "is_active": url.is_active,
            "expires_at": url.expires_at.isoformat() if url.expires_at else None,
            "max_clicks": url.max_clicks,
            "click_count": previous_click_count + 1,
            "webhook_url": url.webhook_url,
            "password_hash": url.password_hash,
        })
        await cache_set(_cache_key(short_code), refreshed)


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
    # Invalidate cache — a cached row would otherwise keep serving
    # redirects for a deleted URL until its TTL expires.
    await cache_delete(_cache_key(url.short_code))
    return True


async def bulk_create_short_urls(
    db: AsyncSession,
    rows: list[dict],
    user_id: int | None = None,
) -> BulkURLResult:
    """
    Shorten many URLs from parsed CSV rows in one request.
    Each row is processed independently — one bad row (invalid URL, etc.)
    does not fail the whole batch. Row numbers are 1-indexed for the
    user-facing report (row 1 = first data row after the header).
    """
    from pydantic import ValidationError

    results: list[BulkURLRow] = []
    for i, row in enumerate(rows, start=1):
        raw_url = (row.get("original_url") or "").strip()
        if not raw_url:
            results.append(
                BulkURLRow(row=i, original_url=raw_url, success=False, error="original_url is empty")
            )
            continue
        try:
            create_data = URLCreate(original_url=raw_url)
            out = await create_short_url(db, create_data, user_id=user_id)
            results.append(
                BulkURLRow(row=i, original_url=raw_url, success=True, short_url=out.short_url)
            )
        except ValidationError:
            results.append(
                BulkURLRow(row=i, original_url=raw_url, success=False, error="invalid URL")
            )

    succeeded = sum(1 for r in results if r.success)
    return BulkURLResult(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )