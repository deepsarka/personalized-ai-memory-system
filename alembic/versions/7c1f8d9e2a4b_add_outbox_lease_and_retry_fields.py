"""add outbox lease and retry fields

Revision ID: 7c1f8d9e2a4b
Revises: 40f45b785c33
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1f8d9e2a4b"
down_revision: Union[str, None] = "40f45b785c33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interaction_events",
        sa.Column("publish_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interaction_events",
        sa.Column("publish_claimed_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "interaction_events",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interaction_events",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interaction_events",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_interaction_events_next_retry_at",
        "interaction_events",
        ["next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interaction_events_next_retry_at",
        table_name="interaction_events",
    )
    op.drop_column("interaction_events", "next_retry_at")
    op.drop_column("interaction_events", "dead_lettered_at")
    op.drop_column("interaction_events", "failed_at")
    op.drop_column("interaction_events", "publish_claimed_by")
    op.drop_column("interaction_events", "publish_claimed_at")
