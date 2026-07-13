"""
Periodic processor for the webhook retry-queue.

Runs every 1 minute via APScheduler inside the existing FastAPI process —
no separate worker, no broker (Celery/Redis-queue) needed. This is a
deliberate trade-off for Render's free tier, which can't reliably host an
always-on worker process.

Backoff strategy: 2 ** retry_count minutes, capped at 5 attempts before a
job is marked 'failed' permanently.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.url import WebhookQueue

logger = logging.getLogger("webhook_queue")

MAX_RETRIES = 5
BATCH_SIZE = 10


async def process_webhook_queue() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(WebhookQueue)
            .where(
                WebhookQueue.status == "pending",
                WebhookQueue.next_retry_at <= now,
            )
            .limit(BATCH_SIZE)
        )
        jobs = result.scalars().all()

        if not jobs:
            return

        async with httpx.AsyncClient(timeout=5.0) as http_client:
            for job in jobs:
                try:
                    response = await http_client.post(job.webhook_url, json=job.payload)
                    if response.is_success:
                        job.status = "success"
                    else:
                        _schedule_retry(job)
                except httpx.HTTPError:
                    _schedule_retry(job)

        await db.commit()


def _schedule_retry(job: WebhookQueue) -> None:
    job.retry_count += 1
    if job.retry_count >= MAX_RETRIES:
        job.status = "failed"
    else:
        job.next_retry_at = datetime.now(timezone.utc) + timedelta(
            minutes=2**job.retry_count
        )


scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(process_webhook_queue, "interval", minutes=1, id="webhook_queue")
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
