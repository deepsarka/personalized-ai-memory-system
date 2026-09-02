from observation.models import ObservationRecord, utcnow
from observation.store import get_observation, save_observation
from uuid import uuid4


def test_observation_exists():
    request_id = str(uuid4())
    record = ObservationRecord(
        request_id=request_id,
        session_id=None,
        subject_id="test-user-001",
        timestamp=utcnow(),
        retrieved_memory_ids=[],
        model="test-model",
        latency_ms=1,
        fallback_used=False,
        response_text="test response",
    )
    save_observation(record)

    found = get_observation(request_id)
    assert found is not None
    assert found.request_id == request_id
    assert found.subject_id == "test-user-001"
    assert found.response_text == "test response"
