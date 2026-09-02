from uuid import uuid4

import pytest

from observation.feedback import FeedbackService
from observation.models import ObservationRecord, utcnow
from observation.store import get_observation, save_observation


def make_observation():
    request_id = str(uuid4())
    save_observation(
        ObservationRecord(
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
    )
    return request_id


def test_positive_feedback():
    request_id = make_observation()
    result = FeedbackService().submit_feedback(request_id, "positive")
    assert result["request_id"] == request_id
    assert result["feedback"] == "positive"
    assert result["feedback_id"]

    record = get_observation(request_id)
    assert record.feedback == "positive"
    assert record.feedback_id == result["feedback_id"]


def test_negative_feedback():
    request_id = make_observation()
    result = FeedbackService().submit_feedback(request_id, "negative")
    assert result["request_id"] == request_id
    assert result["feedback"] == "negative"
    assert result["feedback_id"]

    record = get_observation(request_id)
    assert record.feedback == "negative"
    assert record.feedback_id == result["feedback_id"]


def test_invalid_feedback():
    with pytest.raises(ValueError, match="positive.*negative"):
        FeedbackService().submit_feedback(str(uuid4()), "maybe")


def test_missing_observation():
    request_id = str(uuid4())
    with pytest.raises(ValueError, match="No observation found"):
        FeedbackService().submit_feedback(request_id, "positive")
