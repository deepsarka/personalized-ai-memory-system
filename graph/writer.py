"""
Stage 3 — Temporal Neo4j memory writer.

PostgreSQL is the durable event source of truth.
Neo4j is the derived semantic memory.

Facts are identified by fact_id.

The writer is idempotent so Redpanda at-least-once delivery
cannot create duplicate facts.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from neo4j import (
    AsyncDriver,
    AsyncGraphDatabase,
)

from graph.embeddings import (
    EMBEDDING_DIM,
    embed_text,
)
from processing.schemas import (
    ExtractedFact,
    FactType,
)

load_dotenv()

logger = logging.getLogger("graph.writer")

_driver: AsyncDriver | None = None
_driver_loop: asyncio.AbstractEventLoop | None = None


def _get_driver() -> AsyncDriver:
    global _driver
    global _driver_loop

    current_loop = asyncio.get_running_loop()

    if (
        _driver is None
        or _driver_loop is not current_loop
    ):
        uri = os.getenv(
            "NEO4J_URI",
            "bolt://localhost:7687",
        )

        username = os.getenv(
            "NEO4J_USERNAME",
            os.getenv(
                "NEO4J_USER",
                "neo4j",
            ),
        )

        password = os.getenv(
            "NEO4J_PASSWORD",
            "password",
        )

        _driver = AsyncGraphDatabase.driver(
            uri,
            auth=(
                username,
                password,
            ),
        )

        _driver_loop = current_loop

        logger.info(
            "Neo4j driver initialized: %s",
            uri,
        )

    return _driver


async def init_constraints() -> None:

    driver = _get_driver()

    async with driver.session() as session:

        await session.run(
            """
            CREATE CONSTRAINT subject_id_unique
            IF NOT EXISTS
            FOR (s:Subject)
            REQUIRE s.subject_id IS UNIQUE
            """
        )

        await session.run(
            """
            CREATE CONSTRAINT fact_id_unique
            IF NOT EXISTS
            FOR (f:Fact)
            REQUIRE f.fact_id IS UNIQUE
            """
        )

    logger.info(
        "Neo4j constraints ensured"
    )


async def init_vector_index() -> None:

    driver = _get_driver()

    async with driver.session() as session:

        await session.run(
            """
            CREATE VECTOR INDEX fact_embedding_index
            IF NOT EXISTS
            FOR (f:Fact) ON (f.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """,
            dim=EMBEDDING_DIM,
        )

    logger.info(
        "Neo4j vector index ensured"
    )


async def close_driver() -> None:

    global _driver
    global _driver_loop

    driver = _driver
    driver_loop = _driver_loop

    _driver = None
    _driver_loop = None

    if driver is None:
        return

    # Async Neo4j drivers are bound to the event loop on which they are
    # used. pytest-asyncio/anyio can replace the loop between fixture setup
    # and teardown on Windows. In that situation Neo4j's async close() can
    # reach a dead Proactor and raise AttributeError/RuntimeError. Do not let
    # test cleanup turn an otherwise successful test into an ERROR.
    current_loop = asyncio.get_running_loop()
    if driver_loop is not current_loop:
        logger.warning(
            "Skipping Neo4j async driver close because its event loop is no "
            "longer current (test-loop lifecycle); driver reference released."
        )
        return

    try:
        await driver.close()
    except (AttributeError, RuntimeError) as exc:
        logger.warning("Neo4j driver close skipped after loop shutdown: %s", exc)

    logger.info("Neo4j driver closed")


def _embedding_text(
    fact: ExtractedFact,
) -> str:

    if (
        fact.raw_text
        and fact.raw_text.strip()
    ):
        return fact.raw_text

    return (
        f"{fact.predicate.replace('_', ' ')}: "
        f"{fact.object_value}"
    )


# ======================================================================
# IDEMPOTENT FACT CREATION
# ======================================================================

_CREATE_FACT_QUERY = """
MERGE (f:Fact {
    fact_id: $fact_id
})
ON CREATE SET
    f.predicate = $predicate,
    f.object_value = $object_value,
    f.fact_type = $fact_type,
    f.source = $source,
    f.confidence = $confidence,
    f.policy_class = $policy_class,
    f.valid_from = $valid_from,
    f.valid_until = null,
    f.content_entity_id = $content_entity_id,
    f.source_event_idempotency_key =
        $source_event_idempotency_key,
    f.raw_text = $raw_text,
    f.embedding = $embedding

RETURN f.fact_id AS fact_id,
       f.valid_from AS valid_from
"""


def _is_existing_fact(
    record,
    fact: ExtractedFact,
) -> bool:
    """
    Neo4j MERGE does not directly expose whether CREATE happened.

    This helper is retained for future expansion.
    """

    return False


# ======================================================================
# PREFERENCE / EXCLUSION / CORRECTION
# ======================================================================

_SUPERSEDE_QUERY = """
MERGE (s:Subject {
    subject_id: $subject_id
})

MERGE (f:Fact {
    fact_id: $fact_id
})

ON CREATE SET
    f.predicate = $predicate,
    f.object_value = $object_value,
    f.fact_type = $fact_type,
    f.source = $source,
    f.confidence = $confidence,
    f.policy_class = $policy_class,
    f.valid_from = $valid_from,
    f.valid_until = null,
    f.content_entity_id = $content_entity_id,
    f.source_event_idempotency_key =
        $source_event_idempotency_key,
    f.raw_text = $raw_text,
    f.embedding = $embedding

MERGE (s)-[:HAS_FACT]->(f)

WITH s, f

OPTIONAL MATCH (s)-[:HAS_FACT]->(old:Fact)
WHERE old.fact_id <> $fact_id
  AND old.predicate = $predicate
  AND old.valid_until IS NULL

WITH collect(old) AS old_facts
FOREACH (old IN old_facts | SET old.valid_until = $valid_from)

RETURN size(old_facts) AS superseded_count
"""


# ======================================================================
# BEHAVIOR
# ======================================================================

_APPEND_QUERY = """
MERGE (s:Subject {
    subject_id: $subject_id
})

MERGE (f:Fact {
    fact_id: $fact_id
})

ON CREATE SET
    f.predicate = $predicate,
    f.object_value = $object_value,
    f.fact_type = $fact_type,
    f.source = $source,
    f.confidence = $confidence,
    f.policy_class = $policy_class,
    f.valid_from = $valid_from,
    f.valid_until = null,
    f.content_entity_id = $content_entity_id,
    f.source_event_idempotency_key =
        $source_event_idempotency_key,
    f.raw_text = $raw_text,
    f.embedding = $embedding

MERGE (s)-[:HAS_FACT]->(f)

RETURN f.fact_id AS fact_id
"""


# ======================================================================
# DELETION
# ======================================================================

_DELETE_QUERY = """
MATCH (
    s:Subject {
        subject_id: $subject_id
    }
)-[:HAS_FACT]->(
    old:Fact {
        predicate: $predicate
    }
)

WHERE old.valid_until IS NULL

SET
    old.valid_until = $valid_from,
    old.deleted_reason = 'deletion_request'

RETURN count(old) AS closed_count
"""


async def write_fact(
    fact: ExtractedFact,
) -> dict:

    driver = _get_driver()

    embedding = None

    if fact.fact_type != FactType.DELETION_REQUEST:
        embedding = embed_text(
            _embedding_text(fact)
        )

    params = {
        "subject_id": fact.subject_id,
        "predicate": fact.predicate,
        "object_value": fact.object_value,
        "fact_id": fact.fact_id,
        "fact_type": fact.fact_type.value,
        "source": fact.source.value,
        "confidence": fact.confidence,
        "policy_class": fact.policy_class.value,
        "valid_from": fact.valid_from.isoformat(),
        "content_entity_id": fact.content_entity_id,
        "source_event_idempotency_key":
            fact.source_event_idempotency_key,
        "raw_text": fact.raw_text,
        "embedding": embedding,
    }

    async with driver.session() as session:

        if fact.fact_type == FactType.DELETION_REQUEST:

            result = await session.run(
                _DELETE_QUERY,
                params,
            )

            record = await result.single()

            closed_count = (
                record["closed_count"]
                if record
                else 0
            )

            logger.info(
                "Deletion request: subject=%s predicate=%s closed=%s",
                fact.subject_id,
                fact.predicate,
                closed_count,
            )

            return {
                "action": "deleted",
                "closed_count": closed_count,
                "fact_id": fact.fact_id,
            }

        if fact.fact_type == FactType.BEHAVIOR:

            result = await session.run(
                _APPEND_QUERY,
                params,
            )

            record = await result.single()

            return {
                "action": "appended",
                "fact_id": (
                    record["fact_id"]
                    if record
                    else fact.fact_id
                ),
            }

        result = await session.run(
            _SUPERSEDE_QUERY,
            params,
        )

        record = await result.single()

        superseded_count = (
            record["superseded_count"]
            if record
            else 0
        )

        return {
            "action": "written",
            "superseded_count": superseded_count,
            "fact_id": fact.fact_id,
        }


async def write_facts(
    facts: list[ExtractedFact],
) -> list[dict]:

    outcomes: list[dict] = []

    for fact in facts:

        outcome = await write_fact(
            fact
        )

        outcomes.append(
            outcome
        )

    return outcomes