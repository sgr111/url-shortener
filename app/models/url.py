from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# JSONB on Postgres, plain JSON on SQLite (tests) — same pattern as v4's metadata columns
JSONType = JSON().with_variant(JSONB(), "postgresql")


class URL(Base):
    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Base62-encoded from id — indexed for O(log n) redirect lookup
    # This is the hottest query path in the whole app
    short_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)

    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Expiry options — either by date or by click count (or both)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Soft delete — data preserved for audit, is_active=False stops redirects
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional user-provided webhook — notified via WebhookQueue (retry-safe), not BackgroundTasks
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional password protection — bcrypt hash, never the raw password
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    owner: Mapped["User | None"] = relationship("User", back_populates="urls")  # noqa: F821
    click_events: Mapped[list["ClickEvent"]] = relationship(
        "ClickEvent", back_populates="url", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Composite index — analytics queries filter by user + active status
        Index("idx_user_active", "user_id", "is_active"),
    )


class ClickEvent(Base):
    __tablename__ = "click_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    url_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("urls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max = 45 chars
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    url: Mapped["URL"] = relationship("URL", back_populates="click_events")


class WebhookQueue(Base):
    """
    Postgres-based retry queue for webhook-on-click delivery.

    Why not plain BackgroundTasks: if the webhook POST fails (target down,
    timeout, etc.) a fire-and-forget BackgroundTask just loses the event.
    This table lets a periodic APScheduler job retry failed deliveries with
    exponential backoff, without needing a separate worker process
    (important on Render's free tier, which can't host an always-on worker).
    """

    __tablename__ = "webhook_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    url_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("urls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)  # click data: ip, ts, user-agent

    # pending -> success | failed (after max retries)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )