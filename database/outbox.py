
"""
Durable event ingestion + transactional outbox publisher.

P0.1 - Durable idempotency
--------------------------
PostgreSQL UNIQUE(idempotency_key) is the authoritative idempotency
mechanism.

P0.2 - Transactional outbox
---------------------------
The ingestion path persists the event in PostgreSQL first.

A separate publisher claims durable events and publishes them to
Redpanda.

Delivery semantics:
    AT-LEAST-ONCE

Crash window:

    Redpanda publish succeeds
            |
            X publisher crashes
            |
    PostgreSQL never receives PUBLISHED update
            |
            v
    Lease eventually expires
            |
            v
    Event becomes eligible for republishing

Therefore consumers MUST be idempotent.

Publisher lifecycle:

    ACCEPTED
       |
       v
    PUBLISHING
       |
       +------ publish failure ------> ACCEPTED
       |                                  |
       |                                  v
       |                              retry later
       |
       +------ publish success -----> PUBLISHED

A stale publisher cannot complete another publisher's claim because
publish_claimed_by is checked during the state transition.
"""

import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EventStatus, InteractionEventRecord


logger = logging.getLogger("database.outbox")


# ============================================================================
# Publisher identity
# ============================================================================

# Each application process gets its own unique publisher identity.
#
# hostname alone is not enough because multiple workers may run on the same
# machine/container.
PUBLISHER_ID = f"{socket.gethostname()}:{uuid.uuid4()}"


# ============================================================================
# Configuration
# ============================================================================

PUBLISH_LEASE_SECONDS = max(
    10,
    int(os.getenv("PUBLISH_LEASE_SECONDS", "120")),
)

MAX_RETRY_DELAY_SECONDS = max(
    2,
    int(os.getenv("MAX_RETRY_DELAY_SECONDS", "300")),
)


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ============================================================================
# EVENT INGESTION
# ============================================================================


async def record_event_if_new(
    session: AsyncSession,
    *,
    idempotency_key: str,
    subject_id: str,
    schema_version: str,
    service_id: str,
    surface: str,
    event_type: str,
    consent_state: str,
    raw_text: str | None,
    content_entity_id: str | None,
    event_timestamp: datetime,
    payload: dict,
) -> bool:
    """
    Persist an interaction event exactly once.

    PostgreSQL owns the idempotency guarantee through:

        UNIQUE(idempotency_key)

    Returns:
        True:
            New event inserted.

        False:
            Event already existed.

    The transaction is committed before this function returns so the event
    is durable before the caller continues.
    """

    stmt = (
        pg_insert(InteractionEventRecord)
        .values(
            idempotency_key=idempotency_key,
            subject_id=subject_id,
            schema_version=schema_version,
            service_id=service_id,
            surface=surface,
            event_type=event_type,
            consent_state=consent_state,
            raw_text=raw_text,
            content_entity_id=content_entity_id,
            event_timestamp=event_timestamp,
            status=EventStatus.ACCEPTED,
            payload=payload,
            received_at=utcnow(),
            retry_count=0,
            error_message=None,
            next_retry_at=None,
            publish_claimed_at=None,
            publish_claimed_by=None,
            published_at=None,
            processed_at=None,
            failed_at=None,
            dead_lettered_at=None,
        )
        .on_conflict_do_nothing(
            index_elements=["idempotency_key"],
        )
        .returning(InteractionEventRecord.id)
    )

    result = await session.execute(stmt)

    inserted_id = result.scalar_one_or_none()

    # This event must be durable before returning.
    await session.commit()

    if inserted_id is None:
        logger.info(
            "Duplicate event rejected by PostgreSQL: "
            "idempotency_key=%s",
            idempotency_key,
        )
        return False

    logger.info(
        "Event durably recorded: id=%s idempotency_key=%s",
        inserted_id,
        idempotency_key,
    )

    return True


# ============================================================================
# OUTBOX PUBLISHER
# ============================================================================


async def publish_pending(
    session: AsyncSession,
    event_queue,
    batch_size: int = 100,
) -> int:
    """
    Claim and publish durable outbox events.

    This function deliberately separates:

        1. PostgreSQL claim
        2. Redpanda network I/O
        3. PostgreSQL state update

    We NEVER hold PostgreSQL row locks while waiting for Redpanda.

    Multiple publisher workers can safely run concurrently.

    Lifecycle:

        ACCEPTED
            |
            v
        PUBLISHING
            |
            +---- failure ----> ACCEPTED
            |
            v
        PUBLISHED

    A crashed publisher leaves PUBLISHING behind. Once its lease expires,
    another publisher can reclaim the event.

    Delivery semantics are AT-LEAST-ONCE.
    """

    now = utcnow()

    lease_cutoff = now - timedelta(
        seconds=PUBLISH_LEASE_SECONDS,
    )

    # ------------------------------------------------------------------
    # Phase 1: claim rows
    # ------------------------------------------------------------------

    #
    # IMPORTANT:
    #
    # We select rows with FOR UPDATE SKIP LOCKED, change them to
    # PUBLISHING, and COMMIT before doing Redpanda I/O.
    #
    # This makes the claim visible to other publisher workers.
    #
    claim_stmt = (
        select(InteractionEventRecord)
        .where(
            or_(
                # ------------------------------------------------------
                # Normal pending events.
                # ------------------------------------------------------
                and_(
                    InteractionEventRecord.status
                    == EventStatus.ACCEPTED,
                    InteractionEventRecord.dead_lettered_at.is_(None),
                    or_(
                        InteractionEventRecord.next_retry_at.is_(None),
                        InteractionEventRecord.next_retry_at <= now,
                    ),
                ),

                # ------------------------------------------------------
                # Recover abandoned publisher claims.
                #
                # NULL claimed_at is also considered recoverable.
                # This protects us from malformed/stale rows.
                # ------------------------------------------------------
                and_(
                    InteractionEventRecord.status
                    == EventStatus.PUBLISHING,
                    InteractionEventRecord.dead_lettered_at.is_(None),
                    or_(
                        InteractionEventRecord.publish_claimed_at.is_(None),
                        InteractionEventRecord.publish_claimed_at
                        <= lease_cutoff,
                    ),
                ),
            )
        )
        .order_by(
            InteractionEventRecord.received_at.asc(),
        )
        .limit(batch_size)
        .with_for_update(
            skip_locked=True,
        )
    )

    result = await session.execute(claim_stmt)

    rows = list(result.scalars().all())

    if not rows:
        # Explicitly end any transaction SQLAlchemy may have opened during
        # the SELECT.
        await session.rollback()
        return 0

    # ------------------------------------------------------------------
    # Assign ownership.
    # ------------------------------------------------------------------

    for row in rows:
        row.status = EventStatus.PUBLISHING
        row.publish_claimed_at = now
        row.publish_claimed_by = PUBLISHER_ID

    # ------------------------------------------------------------------
    # IMPORTANT:
    #
    # Commit the claim BEFORE Redpanda I/O.
    # ------------------------------------------------------------------

    await session.commit()

    logger.debug(
        "Claimed %d outbox event(s): publisher=%s",
        len(rows),
        PUBLISHER_ID,
    )

    # ------------------------------------------------------------------
    # Phase 2: publish outside PostgreSQL transaction
    # ------------------------------------------------------------------

    published = 0

    for row in rows:
        try:
            ok = await event_queue.publish(
                row.payload,
            )

            if not ok:
                await _record_publish_failure(
                    session=session,
                    event_id=row.id,
                    error_message="event_queue.publish returned False",
                )
                continue

            # ----------------------------------------------------------
            # Phase 3: mark PUBLISHED.
            # ----------------------------------------------------------

            updated = await _mark_published(
                session=session,
                event_id=row.id,
            )

            if updated:
                published += 1
            else:
                #
                # This is important.
                #
                # Redpanda may already have accepted the event, but the
                # PostgreSQL ownership check failed.
                #
                # DO NOT blindly publish it again here.
                #
                # The event will be recovered/reconciled according to its
                # durable state.
                #
                logger.warning(
                    "Event was published to Redpanda but could not be "
                    "marked PUBLISHED: id=%s publisher=%s",
                    row.id,
                    PUBLISHER_ID,
                )

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Outbox publish failed: id=%s idempotency_key=%s",
                row.id,
                row.idempotency_key,
            )

            await _record_publish_failure(
                session=session,
                event_id=row.id,
                error_message=str(exc)[:2000],
            )

    if published:
        logger.info(
            "Outbox publisher published %d event(s)",
            published,
        )

    return published


# ============================================================================
# MARK PUBLISHED
# ============================================================================


async def _mark_published(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
) -> bool:
    """
    Mark a publisher-owned event as PUBLISHED.

    Ownership is checked using publish_claimed_by.

    This prevents an old publisher from completing a claim that has already
    been recovered by another publisher after the lease expired.
    """

    now = utcnow()

    stmt = (
        update(InteractionEventRecord)
        .where(
            InteractionEventRecord.id == event_id,
            InteractionEventRecord.status
            == EventStatus.PUBLISHING,
            InteractionEventRecord.publish_claimed_by
            == PUBLISHER_ID,
        )
        .values(
            status=EventStatus.PUBLISHED,
            published_at=now,
            publish_claimed_at=None,
            publish_claimed_by=None,
            next_retry_at=None,
            error_message=None,
        )
    )

    result = await session.execute(stmt)

    await session.commit()

    return result.rowcount == 1


# ============================================================================
# RECORD PUBLISH FAILURE
# ============================================================================


async def _record_publish_failure(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    error_message: str,
) -> None:
    """
    Record a Redpanda publishing failure.

    Publishing failure is NOT Stage 2 FAILED.

    Therefore:

        PUBLISHING -> ACCEPTED

    and the event receives a retry time.

    The publisher ownership check is mandatory so an old worker cannot
    overwrite a newer worker's claim.
    """

    result = await session.execute(
        select(
            InteractionEventRecord.retry_count,
        )
        .where(
            InteractionEventRecord.id == event_id,
            InteractionEventRecord.status
            == EventStatus.PUBLISHING,
            InteractionEventRecord.publish_claimed_by
            == PUBLISHER_ID,
        )
    )

    retry_count = result.scalar_one_or_none()

    if retry_count is None:
        #
        # The event is no longer owned by this publisher.
        #
        # Do not modify it.
        #
        logger.warning(
            "Could not record publish failure: "
            "event=%s is no longer owned by publisher=%s",
            event_id,
            PUBLISHER_ID,
        )
        await session.rollback()
        return

    new_retry_count = retry_count + 1

    # ------------------------------------------------------------------
    # Exponential backoff:
    #
    # retry 1 -> 2 seconds
    # retry 2 -> 4 seconds
    # retry 3 -> 8 seconds
    # retry 4 -> 16 seconds
    # ...
    #
    # Maximum delay is controlled by MAX_RETRY_DELAY_SECONDS.
    # ------------------------------------------------------------------

    delay_seconds = min(
        MAX_RETRY_DELAY_SECONDS,
        2 ** min(new_retry_count, 8),
    )

    next_retry_at = utcnow() + timedelta(
        seconds=delay_seconds,
    )

    stmt = (
        update(InteractionEventRecord)
        .where(
            InteractionEventRecord.id == event_id,
            InteractionEventRecord.status
            == EventStatus.PUBLISHING,
            InteractionEventRecord.publish_claimed_by
            == PUBLISHER_ID,
        )
        .values(
            status=EventStatus.ACCEPTED,
            retry_count=new_retry_count,
            next_retry_at=next_retry_at,
            error_message=error_message[:2000],
            publish_claimed_at=None,
            publish_claimed_by=None,
        )
    )

    result = await session.execute(stmt)

    await session.commit()

    if result.rowcount == 1:
        logger.warning(
            "Outbox event returned to ACCEPTED after publish failure: "
            "id=%s retry=%d next_retry=%s",
            event_id,
            new_retry_count,
            next_retry_at,
        )
    else:
        logger.warning(
            "Publish failure update lost ownership race: "
            "event=%s publisher=%s",
            event_id,
            PUBLISHER_ID,
        )


# ============================================================================
# MARK PROCESSED
# ============================================================================


async def mark_processed(
    session: AsyncSession,
    *,
    idempotency_key: str,
    error_message: str | None = None,
) -> None:
    """
    Update the durable event after Stage 2 processing.

    Success:

        PUBLISHED -> PROCESSED

    Processing failure:

        PUBLISHED -> FAILED

    FAILED is intentionally NOT returned to the Redpanda publishing queue.

    Redpanda publication and Stage 2 processing are separate lifecycle
    concerns.
    """

    now = utcnow()

    if error_message:
        stmt = (
            update(InteractionEventRecord)
            .where(
                InteractionEventRecord.idempotency_key
                == idempotency_key,
                InteractionEventRecord.status
                == EventStatus.PUBLISHED,
            )
            .values(
                status=EventStatus.FAILED,
                processed_at=now,
                failed_at=now,
                error_message=error_message[:2000],
            )
        )
    else:
        stmt = (
            update(InteractionEventRecord)
            .where(
                InteractionEventRecord.idempotency_key
                == idempotency_key,
                InteractionEventRecord.status
                == EventStatus.PUBLISHED,
            )
            .values(
                status=EventStatus.PROCESSED,
                processed_at=now,
                failed_at=None,
                error_message=None,
            )
        )

    result = await session.execute(stmt)

    await session.commit()

    if result.rowcount == 0:
        logger.warning(
            "Could not mark event processed: "
            "idempotency_key=%s was not in PUBLISHED state",
            idempotency_key,
        )

