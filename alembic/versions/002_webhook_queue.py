"""Add webhook_queue table and urls.webhook_url column

Revision ID: 002
Revises: 001
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("urls", sa.Column("webhook_url", sa.Text(), nullable=True))

    op.create_table(
        "webhook_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url_id", sa.Integer(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_queue_id", "webhook_queue", ["id"])
    op.create_index("ix_webhook_queue_url_id", "webhook_queue", ["url_id"])
    # Speeds up the scheduler's poll query: status='pending' AND next_retry_at <= now
    op.create_index("idx_webhook_status_retry", "webhook_queue", ["status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("idx_webhook_status_retry", table_name="webhook_queue")
    op.drop_index("ix_webhook_queue_url_id", table_name="webhook_queue")
    op.drop_index("ix_webhook_queue_id", table_name="webhook_queue")
    op.drop_table("webhook_queue")
    op.drop_column("urls", "webhook_url")
