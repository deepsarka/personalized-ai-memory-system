import pytest

from graph.writer import write_fact


@pytest.mark.anyio
async def test_preference_supersession():

    # This test assumes your Neo4j database is running.
    # Use a unique fact_id/event_id so previous test runs
    # do not trigger the idempotency check.

    from processing.schemas import (
        ExtractedFact,
        FactType,
        FactSource,
        PolicyClass,
    )
    from datetime import datetime, timezone

    # ---------------------------------------------------------
    # 1. Write the OLD preference
    # ---------------------------------------------------------

    old_fact = ExtractedFact(
        fact_id="pytest-old-rock-test-004",
        subject_id="pytest-user-graph",
        source=FactSource.EXPLICIT,
        confidence=1.0,
        policy_class=PolicyClass.STANDARD,
        fact_type=FactType.PREFERENCE,
        predicate="prefers_genre",
        object_value="edm",
        content_entity_id=None,
        valid_from=datetime.now(timezone.utc),
        valid_until=None,
        source_event_idempotency_key="pytest-old-event-004",
        raw_text="I like EDM.",
    )

    await write_fact(old_fact)

    # ---------------------------------------------------------
    # 2. Write the NEW preference
    # ---------------------------------------------------------

    new_fact = ExtractedFact(
        fact_id="pytest-new-rock-test-005",
        subject_id="pytest-user-graph",
        source=FactSource.EXPLICIT,
        confidence=1.0,
        policy_class=PolicyClass.STANDARD,
        fact_type=FactType.PREFERENCE,
        predicate="prefers_genre",
        object_value="rock",
        content_entity_id=None,
        valid_from=datetime.now(timezone.utc),
        valid_until=None,
        source_event_idempotency_key="pytest-new-event-005",
        raw_text="I prefer rock now.",
    )

    result = await write_fact(new_fact)

    # ---------------------------------------------------------
    # 3. Verify supersession
    # ---------------------------------------------------------

    assert result["action"] == "written"
    assert result["superseded_count"] >= 1