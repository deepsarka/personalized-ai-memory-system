"""
Stage 8.1/8.3 — Observation model (Postgres-backed).

One row per generated /chat response, extended with feedback fields so a
later thumbs-up/down can attach to the same row rather than needing a
second table/join.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from database.models import Base


class ObservationRecord(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)

    request_id = Column(String(36), unique=True, nullable=False, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    subject_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # Retrieval / provenance
    retrieved_memory_ids = Column(JSON, nullable=False, default=list)

    # Generation
    model = Column(String(100), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    fallback_used = Column(Boolean, nullable=False, default=False)
    response_text = Column(Text, nullable=True)

    # Feedback (Stage 8.3) — nullable until/unless the user actually reacts
    feedback_id = Column(String(36), nullable=True)
    feedback = Column(String(20), nullable=True)  # "positive" | "negative"

    def __repr__(self) -> str:
        return f"<ObservationRecord request_id={self.request_id} subject_id={self.subject_id}>"


def new_request_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)