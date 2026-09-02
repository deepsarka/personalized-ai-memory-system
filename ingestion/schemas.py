"""
Stage 1 — Capture and authorize.

Defines the typed, versioned schema every interaction event must conform to
before it's accepted into the pipeline. This is the contract referenced by
your course instructions: "An AI surface emits a versioned interaction event."
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SurfaceType(str, Enum):
    """Which AI surface emitted this event — maps to the journeys in the spec."""

    CHAT_ASSISTANT = "chat_assistant"
    DISCOVERY = "discovery"
    PLAYLIST = "playlist"
    PODCAST = "podcast"


class EventType(str, Enum):
    """What kind of interaction this is."""

    EXPLICIT_STATEMENT = "explicit_statement"  # user directly said something
    IMPLICIT_BEHAVIOR = (
        "implicit_behavior"  # inferred from listening/skip behavior
    )
    CORRECTION = "correction"  # user corrected a prior memory
    DELETION_REQUEST = "deletion_request"  # user asked to forget something


class ConsentState(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    NOT_SET = "not_set"


class InteractionEvent(BaseModel):
    """
    A single versioned interaction event submitted by an AI surface.
    This is the ONLY shape of data the ingestion API will accept — anything
    that doesn't validate against this schema is rejected before it reaches
    the queue.
    """

    model_config = ConfigDict(use_enum_values=True)

    # --- Identity & authorization fields (required by Stage 1 spec) ---
    schema_version: str = Field(..., description="Schema version, e.g. '1.0'")
    service_id: str = Field(
        ..., description="Identity of the emitting AI surface/service"
    )
    subject_id: str = Field(
        ..., description="The user/listener this event is about"
    )
    consent_state: ConsentState = Field(
        ..., description="Consent status at capture time"
    )
    idempotency_key: str = Field(
        ..., description="Unique key to prevent duplicate processing"
    )

    # --- Event content ---
    surface: SurfaceType
    event_type: EventType
    raw_text: Optional[str] = Field(
        None, description="Raw text of what was said/typed, if applicable"
    )
    content_entity_id: Optional[str] = Field(
        None,
        description=(
            "Related content entity (track, playlist, episode) if applicable"
        ),
    )

    # --- Timing ---
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the interaction occurred",
    )

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v not in {"1.0"}:
            raise ValueError(
                f"Unsupported schema_version: {v}. Expected '1.0'."
            )
        return v

    @field_validator("subject_id", "service_id", "idempotency_key")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty")
        return v


class IngestionResult(BaseModel):
    """Response returned to the calling AI surface after ingestion attempt."""

    accepted: bool
    idempotency_key: str
    reason: Optional[str] = None
    queued_at: Optional[datetime] = None