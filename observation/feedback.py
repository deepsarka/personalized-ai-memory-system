"""
Stage 8.3 — Feedback service.

No-arg constructor (matches how composition/api.py already calls
FeedbackService() with nothing) -- talks to the module-level store
functions directly rather than taking an injected store object, matching
the function-based style of observation/store.py.
"""

import uuid

from observation.store import update_feedback

VALID_FEEDBACK = {"positive", "negative"}


class FeedbackService:
    def submit_feedback(self, request_id: str, feedback: str) -> dict:
        feedback = feedback.lower().strip()

        if feedback not in VALID_FEEDBACK:
            raise ValueError("Feedback must be 'positive' or 'negative'.")

        feedback_id = str(uuid.uuid4())

        updated = update_feedback(
            request_id=request_id,
            feedback=feedback,
            feedback_id=feedback_id,
        )

        if not updated:
            raise ValueError(f"No observation found for request_id={request_id}")

        return {
            "feedback_id": feedback_id,
            "request_id": request_id,
            "feedback": feedback,
        }