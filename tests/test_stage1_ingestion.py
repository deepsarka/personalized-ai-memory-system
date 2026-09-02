import pytest
from datetime import datetime, timezone, timedelta

from database.connection import AsyncSessionLocal
from ingestion.api import ingest_event
from ingestion.schemas import InteractionEvent


def make_event(**overrides):
    data = {
        "schema_version": "1.0",
        "service_id": "test-service",
        "subject_id": "test-user-001",
        "consent_state": "granted",
        "idempotency_key": "pytest-stage1-001",
        "surface": "chat_assistant",
        "event_type": "explicit_statement",
        "raw_text": "I like rock music.",
        "content_entity_id": None,
        "timestamp": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return InteractionEvent(**data)


async def call_ingest(event):
    # ingest_event is a FastAPI handler, so dependency injection normally
    # supplies db. Direct tests must provide the real AsyncSession explicitly.
    async with AsyncSessionLocal() as db:
        return await ingest_event(event, db=db)


@pytest.mark.anyio
async def test_valid_event_is_accepted():
    event = make_event(idempotency_key="pytest-stage1-valid-001")
    result = await call_ingest(event)
    assert result.accepted is True
    assert result.idempotency_key == "pytest-stage1-valid-001"


@pytest.mark.anyio
async def test_event_without_consent_is_rejected():
    event = make_event(
        idempotency_key="pytest-stage1-consent-001",
        consent_state="denied",
    )
    result = await call_ingest(event)
    assert result.accepted is False
    assert "consent_not_granted" in result.reason


@pytest.mark.anyio
async def test_duplicate_event_is_rejected():
    key = "pytest-stage1-duplicate-001"
    result1 = await call_ingest(make_event(idempotency_key=key))
    result2 = await call_ingest(make_event(idempotency_key=key))
    assert result1.accepted is True
    assert result2.accepted is False
    assert result2.reason == "duplicate_idempotency_key"


@pytest.mark.anyio
async def test_future_timestamp_is_rejected():
    event = make_event(
        idempotency_key="pytest-stage1-future-001",
        timestamp=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    result = await call_ingest(event)
    assert result.accepted is False
    assert result.reason == "timestamp_in_future"
