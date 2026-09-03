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
    fact_type: FactType = FactType.PREFERENCE,
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
        fact_type=fact_type,
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


# ---------------------------------------------------------------------------
# Supersession / correction regression tests.
#
# graph/writer.py's _SUPERSEDE_QUERY used to match superseding facts on
# predicate alone, ignoring object_value. That caused two bugs reported in
# production:
#
#   1. Stating two simultaneous preferences of the same predicate (e.g.
#      "I love jazz and lo-fi") silently closed the first one, because the
#      second write's supersede query matched ANY old fact with the same
#      predicate, regardless of object_value.
#
#   2. An explicit rejection ("I don't like jazz anymore") produces an
#      excludes_genre/jazz fact (see processing/extractor.py's correction
#      normalization), but that fact's supersede query only looked for old
#      facts with predicate=excludes_genre -- the original preference was
#      stored as predicate=prefers_genre, a different string, so it was
#      never closed and kept resurfacing as "still valid" after the
#      correction.
#
# These tests write facts directly via graph.writer.write_fact (bypassing
# Gemini extraction, which isn't available/deterministic in CI) to pin down
# the graph-level contract precisely.
# ---------------------------------------------------------------------------


async def _facts_for_subject(retriever, subject_id: str, query: str = "What music do I like?", top_k: int = 20):
    embedder = QueryEmbedder()
    query_embedding = embedder.embed(query)
    return retriever.retrieve(
        query_embedding,
        RetrievalQuery(subject_id=subject_id, query=query, top_k=top_k),
    )


@pytest.mark.asyncio
async def test_two_simultaneous_preferences_both_remain_valid(retriever):
    """
    Stating two preferences under the same predicate (two liked genres)
    must NOT cause the first to supersede the second. Before the fix, the
    second write's broad predicate-only match silently closed the first.
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"

    jazz = _make_fact(subject_id, object_value="jazz", predicate="prefers_genre")
    await write_fact(jazz)

    lofi = _make_fact(subject_id, object_value="lo-fi", predicate="prefers_genre")
    await write_fact(lofi)

    results = await _facts_for_subject(retriever, subject_id)
    returned_ids = {r.fact_id for r in results}

    assert jazz.fact_id in returned_ids, "earlier preference was wrongly superseded by a later, unrelated one"
    assert lofi.fact_id in returned_ids


@pytest.mark.asyncio
async def test_exclusion_closes_matching_preference(retriever):
    """
    An exclusion (excludes_genre/X) must close the earlier preference
    (prefers_genre/X) for the SAME object_value. This is the exact bug
    reported in production: rejecting a genre didn't stop it from being
    recommended, because excludes_genre and prefers_genre are different
    predicate strings and the old query never matched them together.
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"

    lofi_pref = _make_fact(subject_id, object_value="lo-fi", predicate="prefers_genre")
    await write_fact(lofi_pref)

    lofi_exclusion = _make_fact(
        subject_id,
        object_value="lo-fi",
        predicate="excludes_genre",
        fact_type=FactType.EXCLUSION,
    )
    await write_fact(lofi_exclusion)

    results = await _facts_for_subject(retriever, subject_id)
    returned_ids = {r.fact_id for r in results}

    assert lofi_pref.fact_id not in returned_ids, "rejected preference is still 'valid' and being recommended"
    assert lofi_exclusion.fact_id in returned_ids


@pytest.mark.asyncio
async def test_exclusion_does_not_close_unrelated_preference(retriever):
    """
    Excluding one genre must not close a *different* genre's preference.
    Guards against an overcorrection where the fix above is made too broad
    (e.g. matching on predicate alone instead of predicate+object_value).
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"

    jazz_pref = _make_fact(subject_id, object_value="jazz", predicate="prefers_genre")
    await write_fact(jazz_pref)

    lofi_exclusion = _make_fact(
        subject_id,
        object_value="lo-fi",
        predicate="excludes_genre",
        fact_type=FactType.EXCLUSION,
    )
    await write_fact(lofi_exclusion)

    results = await _facts_for_subject(retriever, subject_id)
    returned_ids = {r.fact_id for r in results}

    assert jazz_pref.fact_id in returned_ids, "unrelated preference was wrongly closed by an exclusion of a different value"


@pytest.mark.asyncio
async def test_correction_broadly_replaces_single_valued_predicate(retriever):
    """
    A genuine correction (fact_type=correction), used for single-valued
    predicates like tempo, should still broadly replace ANY prior value
    under that predicate -- this is the one case where predicate-only
    matching is intentional and must keep working.
    """
    subject_id = f"test-subject-{uuid.uuid4().hex}"

    energetic = _make_fact(subject_id, object_value="energetic", predicate="prefers_tempo")
    await write_fact(energetic)

    calm = _make_fact(
        subject_id,
        object_value="calm",
        predicate="prefers_tempo",
        fact_type=FactType.CORRECTION,
    )
    await write_fact(calm)

    results = await _facts_for_subject(retriever, subject_id)
    returned_ids = {r.fact_id for r in results}

    assert energetic.fact_id not in returned_ids, "correction did not replace the old single-valued preference"
    assert calm.fact_id in returned_ids