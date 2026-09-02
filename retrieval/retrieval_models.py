from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    subject_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedFact(BaseModel):
    fact_id: Optional[str] = None
    subject_id: str
    fact_type: str
    predicate: str
    object_value: str
    source: str
    policy_class: str
    raw_text: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    similarity: float


class RetrievalResult(BaseModel):
    query: str
    subject_id: str
    facts: list[RetrievedFact] = []