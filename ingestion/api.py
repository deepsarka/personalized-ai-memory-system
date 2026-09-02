"""
Stage 1 — Capture and authorize.

FastAPI router implementing the ingestion API described in your course spec:

    "An AI surface emits a versioned interaction event. The ingestion API
    verifies service identity, subject scope, consent state, schema version,
    timestamp, and idempotency key. Accepted events enter a durable queue
    so graph processing does not block the experience."

This is Stage 1 of 6 in the lifecycle diagram. It does NOT write to the graph —
that's Stage 3, handled downstream after a consumer reads off the queue.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.schemas import InteractionEvent, IngestionResult, ConsentState
from database.connection import get_db
from database.outbox import record_event_if_new

logger = logging.getLogger("ingestion.api")
router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/event", response_model=IngestionResult, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    event: InteractionEvent, db: AsyncSession = Depends(get_db)
) -> IngestionResult:
    """
    Accept a single interaction event from an AI surface.

    Validation order matches the spec: identity -> subject scope -> consent ->
    schema version -> timestamp -> idempotency. Each check fails fast with a
    clear reason, since operators need to know exactly why an event was rejected
    (per the Non-Functional Expectations: 'auditable', 'explainable').
    """

    # 1. Service identity check (placeholder for real auth — e.g. verify a
    #    signed service token here in production; the schema requires the field
    #    to be present and non-empty, which Pydantic already enforced).
    if not event.service_id:
        return _reject(event, "missing_service_identity")

    # 2. Subject scope check — must have a valid subject to attach memory to.
    if not event.subject_id:
        return _reject(event, "missing_subject_scope")

    # 3. Consent check — refuse to even queue an event without granted consent.
    #    This is a privacy-by-design control, not just a filter applied later.
    if event.consent_state != ConsentState.GRANTED.value and event.consent_state != ConsentState.GRANTED:
        return _reject(event, f"consent_not_granted:{event.consent_state}")

    # 4. Schema version — already validated by Pydantic at parse time, but we
    #    double-check here in case this endpoint is ever called with a raw dict.
    if event.schema_version != "1.0":
        return _reject(event, f"unsupported_schema_version:{event.schema_version}")

    # 5. Timestamp sanity check — reject events timestamped too far in the future
    #    (clock skew / bad client), which would corrupt temporal graph ordering.
    now = datetime.now(timezone.utc)
    event_ts = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
    if event_ts > now.replace(microsecond=0) and (event_ts - now).total_seconds() > 60:
        return _reject(event, "timestamp_in_future")

    # 6. Idempotency check — now durable (Postgres UNIQUE constraint via
    #    INSERT ... ON CONFLICT DO NOTHING), not a process-local set. This
    #    also *is* the outbox insert: the row lands with status=accepted
    #    and a separate publisher step (see database/outbox.py, wired into
    #    api/main.py's background loop and /process/run) hands it to
    #    Redpanda. Ingestion no longer talks to Redpanda directly, so a
    #    crash between "recorded" and "published" can't lose the event —
    #    it's sitting in Postgres either way.
    is_new = await record_event_if_new(
        db,
        idempotency_key=event.idempotency_key,
        subject_id=event.subject_id,
        schema_version=event.schema_version,
        service_id=event.service_id,
        surface=event.surface,
        event_type=event.event_type,
        consent_state=event.consent_state,
        raw_text=event.raw_text,
        content_entity_id=event.content_entity_id,
        event_timestamp=event_ts,
        payload=event.model_dump(mode="json"),
    )

    if not is_new:
        logger.info(f"Duplicate event rejected: {event.idempotency_key}")
        return IngestionResult(
            accepted=False,
            idempotency_key=event.idempotency_key,
            reason="duplicate_idempotency_key",
        )

    logger.info(f"Event accepted and durably recorded: {event.idempotency_key} ({event.event_type})")
    return IngestionResult(
        accepted=True,
        idempotency_key=event.idempotency_key,
        queued_at=now,
    )


def _reject(event: InteractionEvent, reason: str) -> IngestionResult:
    logger.warning(f"Event rejected ({reason}): key={event.idempotency_key}")
    return IngestionResult(
        accepted=False,
        idempotency_key=event.idempotency_key,
        reason=reason,
    )
