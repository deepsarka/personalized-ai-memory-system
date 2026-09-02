"""initial schema — users, interaction_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-29

Hand-written to match database/models.py exactly, since this environment
has no live Postgres to autogenerate against. Run `alembic upgrade head`
against a real database before deploying; if drift is suspected, run
`alembic revision --autogenerate` and diff its output against this file
rather than trusting this blind.

Note: users.id is NOT referenced by interaction_events — subject_id is
stored as a plain string on events. See database/models.py's User
docstring for why (no account-creation flow exists yet to populate it).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "interaction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("service_id", sa.String(length=255), nullable=False),
        sa.Column("surface", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("consent_state", sa.String(length=30), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("content_entity_id", sa.String(length=255), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="accepted"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_interaction_events_idempotency_key",
        "interaction_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_interaction_events_subject_id", "interaction_events", ["subject_id"]
    )
    op.create_index(
        "ix_interaction_events_content_entity_id", "interaction_events", ["content_entity_id"]
    )
    op.create_index(
        "ix_interaction_events_status_received_at",
        "interaction_events",
        ["status", "received_at"],
    )


def downgrade() -> None:
    op.drop_table("interaction_events")
    op.drop_table("users")
