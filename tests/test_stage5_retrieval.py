"""
Stage 5 — retrieval integration tests.

These are the tests that were missing: everything else that touches
"retrieval" in this suite (test_stage9_end_to_end.py) mocks the retriever
out with hand-built FakeFact objects and never calls FactRetriever against
a real Neo4j instance. That gap is exactly how the valid_from/valid_until
type bug (facts written as ISO strings, queried against Cypher's native
datetime()) went uncaught: governance/reranker logic looked correct in
isolation, but the retrieval query silently returned zero rows for every
subject, always.

These tests write a fact through the real Stage 3 writer, then read it
back through the real Stage 4/5 retriever, so a regression here fails
loudly instead of just returning empty results in production.

Requires a live Neo4j (see conftest.py's setup_neo4j_database fixture,
same as test_stage3_graph.py).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from graph.writer import write_fact
from processing.schemas import (
    ExtractedFact,
    FactSource,
    FactType,
    PolicyClass,
)
from retrieval.embedding import QueryEmbedder
from retrieval.retrieval_models import RetrievalQuery
from retrieval.retriever import FactRetriever


def _make_fact(
    subject_id: str,
    object_value: str = "classical",
    predicate: str = "prefers_genre",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> ExtractedFact:
    key = f"test-{uuid.uuid4().hex}"
    return ExtractedFact(
        fact_id=f"{key}-fact0",
        subject_id=subject_id,
        source=FactSource.EXPLICIT,
        confidence=0.9,
        policy_class=PolicyClass.STANDARD,
        fact_type=FactType.PREFERENCE,
        predicate=predicate,
        object_value=object_value,
        valid_from=valid_from or datetime.now(timezone.utc),
        valid_until=valid_until,
        source_event_idempotency_key=key,
        raw_text=f"I like {object_value} music",
    )


@pytest.fixture
def retriever():
    r = FactRetriever(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="testpassword123",
    )
    yield r
    r.close()


@pytest.mark.asyncio
async def test_written_fact_is_retrievable(retriever):
    """
    A fact written via Stage 3 must come back via Stage 5 retrieval.

    This is the core regression test: with the valid_from/valid_until
    type-mismatch bug, this fact would be written successfully (Stage 3
    has no knowledge of the retrieval query) but `retriever.retrieve()`
    would come back empty, because `node.valid_from <= datetime()`
    silently evaluates to null when node.valid_from is a string.
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"
    fact = _make_fact(subject_id, object_value="classical")

    await write_fact(fact)

    embedder = QueryEmbedder()
    query_embedding = embedder.embed("What kind of music do I like?")

    results = retriever.retrieve(
        query_embedding,
        RetrievalQuery(subject_id=subject_id, query="What kind of music do I like?", top_k=5),
    )

    assert len(results) >= 1
    assert any(r.fact_id == fact.fact_id for r in results)
    match = next(r for r in results if r.fact_id == fact.fact_id)
    assert match.subject_id == subject_id
    assert match.object_value == "classical"


@pytest.mark.asyncio
async def test_expired_fact_is_not_retrieved(retriever):
    """
    A fact whose valid_until is in the past must not be retrieved.

    Also guards against the inverse failure mode: if the type-mismatch
    fix were done by dropping the temporal filter entirely rather than
    comparing like-for-like types, expired facts would leak back in.
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    fact = _make_fact(
        subject_id,
        object_value="jazz",
        valid_from=now - timedelta(days=2),
        valid_until=now - timedelta(days=1),
    )

    await write_fact(fact)

    embedder = QueryEmbedder()
    query_embedding = embedder.embed("What kind of music do I like?")

    results = retriever.retrieve(
        query_embedding,
        RetrievalQuery(subject_id=subject_id, query="What kind of music do I like?", top_k=5),
    )

    assert all(r.fact_id != fact.fact_id for r in results)


@pytest.mark.asyncio
async def test_future_fact_is_not_retrieved(retriever):
    """A fact whose valid_from is in the future must not be retrieved yet."""
    subject_id = f"test-subject-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    fact = _make_fact(
        subject_id,
        object_value="ambient",
        valid_from=now + timedelta(days=1),
    )

    await write_fact(fact)

    embedder = QueryEmbedder()
    query_embedding = embedder.embed("What kind of music do I like?")

    results = retriever.retrieve(
        query_embedding,
        RetrievalQuery(subject_id=subject_id, query="What kind of music do I like?", top_k=5),
    )

    assert all(r.fact_id != fact.fact_id for r in results)