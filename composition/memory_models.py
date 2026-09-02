from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MemoryItem(BaseModel):
    fact_id: str
    subject_id: str
    fact_type: str
    predicate: str
    object_value: str
    source: str
    policy_class: str

    valid_from: datetime
    valid_until: datetime | None

    relevance_score: float


class MemoryPackage(BaseModel):
    subject_id: str
    query: str

    memories: list[MemoryItem]

    memory_available: bool
    fallback_reason: Optional[str] = None