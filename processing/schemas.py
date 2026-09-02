"""
Stage 2 — Normalize and resolve: output schema.

This is the typed shape every raw interaction event gets turned into before
it's eligible to be written to the graph (Stage 3). Matches your spec's
governance requirement: "Every retained memory must have a defined subject,
source, confidence, timestamp, policy class, and retention behavior."
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FactSource(str, Enum):
    EXPLICIT = "explicit"        # user directly stated it
    INFERRED = "inferred"        # derived from behavior
    CORRECTION = "correction"    # user corrected a prior fact


class PolicyClass(str, Enum):
    """
    Sensitivity/retention tier. Deliberately conservative: anything that
    isn't clearly a safe preference/behavior fact gets classified RESTRICTED
    and filtered out downstream rather than risk storing something sensitive.
    """
    STANDARD = "standard"          # ordinary preference/behavior — normal retention
    SHORT_LIVED = "short_lived"    # likely momentary, short default expiry
    RESTRICTED = "restricted"      # sensitive or ambiguous — not persisted in this pilot


class FactType(str, Enum):
    PREFERENCE = "preference"          # "I like calmer music in the evening"
    EXCLUSION = "exclusion"            # "don't recommend X anymore"
    BEHAVIOR = "behavior"              # inferred from repeated actions
    CORRECTION = "correction"          # overrides a prior fact
    DELETION_REQUEST = "deletion_request"


class ExtractedFact(BaseModel):
    """
    A single normalized, typed fact ready for graph write (Stage 3) or
    rejection. Every field here is required precisely because the governance
    model requires it — no fact reaches the graph without all of these set.
    """
    fact_id: str = Field(..., description="Deterministic ID derived from source event")
    subject_id: str
    source: FactSource
    confidence: float = Field(..., ge=0.0, le=1.0)
    policy_class: PolicyClass
    fact_type: FactType

    predicate: str = Field(..., description="What kind of relationship/attribute, e.g. 'prefers_mood'")
    object_value: str = Field(..., description="The value, e.g. 'calm'")
    content_entity_id: Optional[str] = None

    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = Field(
        None, description="Explicit expiry if known; None means governed by policy_class default"
    )

    source_event_idempotency_key: str
    raw_text: Optional[str] = None


class ProcessingResult(BaseModel):
    """Outcome of running Stage 2 over one raw event."""
    source_event_idempotency_key: str
    accepted_facts: list[ExtractedFact] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)
