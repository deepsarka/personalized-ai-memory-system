"""
Application-level PostgreSQL models.

PostgreSQL stores durable application records.
Neo4j stores the derived graph/semantic representation.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """
    Return a timezone-aware UTC datetime.
    """

    return datetime.now(timezone.utc)


class EventStatus:
    """
    Durable lifecycle for an interaction event.

    ACCEPTED:
        Event is durably stored in PostgreSQL and is waiting
        for Redpanda publication.

    PUBLISHING:
        Event has been claimed by one outbox worker and is
        currently being published to Redpanda.

    PUBLISHED:
        Redpanda publication succeeded.

    PROCESSED:
        Stage 2 extraction + graph processing succeeded.

    FAILED:
        Stage 2 processing failed.

    Important:

        FAILED is NOT a Redpanda publishing failure.

        A Redpanda publishing failure returns the event to
        ACCEPTED with retry metadata.
    """

    ACCEPTED = "accepted"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PROCESSED = "processed"
    FAILED = "failed"


class User(Base):
    """
    Application identity.

    subject_id remains independent from User.id for now because the
    ingestion/event pipeline currently uses subject_id as its identity
    concept.

    When authentication is fully integrated, subject_id can be linked
    to User.id through the application identity layer.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="user",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class InteractionEventRecord(Base):
    """
    Durable interaction event and transactional outbox record.

    PostgreSQL is the authoritative event registry.

    Lifecycle:

        ACCEPTED
            |
            v
        PUBLISHING
            |
            +---- publish failure ---> ACCEPTED
            |
            v
        PUBLISHED
            |
            +---- processing failure ---> FAILED
            |
            v
        PROCESSED

    Delivery semantics are AT-LEAST-ONCE.

    A crash after Redpanda accepts the event but before PostgreSQL
    records PUBLISHED can result in a duplicate Redpanda message.

    Therefore the consumer MUST remain idempotent.
    """

    __tablename__ = "interaction_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    subject_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    schema_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    service_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    surface: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    consent_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content_entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    # --------------------------------------------------------------
    # Outbox lifecycle
    # --------------------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=EventStatus.ACCEPTED,
        index=True,
    )

    # --------------------------------------------------------------
    # Publisher lease / claim
    # --------------------------------------------------------------

    publish_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    publish_claimed_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # --------------------------------------------------------------
    # Publication state
    # --------------------------------------------------------------

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --------------------------------------------------------------
    # Processing state
    # --------------------------------------------------------------

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --------------------------------------------------------------
    # Retry state
    # --------------------------------------------------------------

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # --------------------------------------------------------------
    # Original event payload
    # --------------------------------------------------------------

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_interaction_events_status_received_at",
            "status",
            "received_at",
        ),
        Index(
            "ix_interaction_events_next_retry_at",
            "next_retry_at",
        ),
    )