"""
Redirect endpoint — the hottest path in the entire application.

Flow:
  1. Lookup short_code in DB (indexed → fast)
  2. Validate: active? not expired? under click limit?
  3. Atomic click_count increment in DB
  4. Send 302 redirect response immediately
  5. Log click event as BackgroundTask (after response sent)
     → keeps redirect latency low, no blocking I/O in hot path

This is the key design decision: background logging lets us
keep p99 redirect latency low even when DB write is slow.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.db.session import get_db
from app.services import url_service

router = APIRouter(tags=["Redirect"])


@router.get("/{short_code}")
async def redirect_to_original(
    request: Request,
    short_code: str,
    background_tasks: BackgroundTasks,
    password: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    url = await url_service.get_url_by_code(db, short_code)

    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found",
        )

    is_valid, reason = url_service.check_url_validity(url)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=reason,
        )

    # Password-protected links: checked before counting the click or
    # firing webhooks, so a wrong/missing password never triggers either.
    if not url_service.check_password(url, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password required or incorrect. Pass it as ?password=...",
        )

    # Atomic increment — avoids race condition under concurrent traffic
    await url_service.increment_click_count(db, url, short_code=short_code)

    # Log click event AFTER redirect response is sent
    # Uses a new session inside the background task
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    background_tasks.add_task(
        url_service.log_click_event,
        db,
        url.id,
        ip,
        user_agent,
        country=None,  # Future: fetch from ip-api.com via httpx
    )

    # If the owner set a webhook_url, enqueue a retry-safe delivery job
    # instead of firing the webhook directly — a plain BackgroundTask would
    # lose the notification if the target endpoint is down or times out.
    if url.webhook_url:
        background_tasks.add_task(
            url_service.enqueue_webhook_job,
            db,
            url.id,
            url.webhook_url,
            ip,
            user_agent,
        )

    return RedirectResponse(url=str(url.original_url), status_code=status.HTTP_302_FOUND)