"""
Stage 2 — consumer.

Reads events from Redpanda (or the in-memory fallback), runs Stage 2
extraction, writes accepted facts to Neo4j, updates the durable event
status in PostgreSQL, and commits Redpanda offsets only after successful
processing.

Pipeline:

PostgreSQL Outbox
        ↓
    Redpanda
        ↓
   ConsumedEvent
        ↓
  FactExtractor
        ↓
     Neo4j
        ↓
  mark_processed()
        ↓
 Redpanda commit

Important:
Kafka offsets are committed only through the highest contiguous sequence
of successfully processed events for each partition.
"""

import asyncio
import logging

from database.connection import AsyncSessionLocal
from database.outbox import mark_processed, publish_pending
from graph.writer import write_facts
from ingestion.queue import ConsumedEvent, event_queue
from processing.extractor import FactExtractor
from processing.schemas import ProcessingResult


logger = logging.getLogger("processing.consumer")


async def process_pending_events(
    max_events: int = 50,
) -> list[ProcessingResult]:
    """
    Drain up to `max_events` events from the queue.

    For each event:

    1. Extract facts using Stage 2.
    2. Write accepted facts to Neo4j.
    3. Mark the durable PostgreSQL event as processed/failed.
    4. Commit Redpanda offsets only through the highest contiguous
       successfully processed event per partition.

    This prevents a later successful event from causing an earlier
    failed event to be skipped.
    """

    extractor = FactExtractor()

    results: list[ProcessingResult] = []

    consumed_events: list[ConsumedEvent] = (
        await event_queue.consume_available(
            max_events=max_events,
        )
    )

    if not consumed_events:
        return results

    # Track the processing outcome of every consumed event.
    #
    # True  -> fully successful
    # False -> failed / must be redelivered
    processing_success: dict[int, bool] = {}

    async with AsyncSessionLocal() as db:

        for index, consumed_event in enumerate(consumed_events):

            raw_event = consumed_event.event

            idempotency_key = raw_event.get(
                "idempotency_key",
                "",
            )

            try:

                # --------------------------------------------------
                # Stage 2 — extraction
                # --------------------------------------------------

                result = extractor.extract(
                    raw_text=raw_event.get(
                        "raw_text"
                    ) or "",
                    subject_id=raw_event.get(
                        "subject_id",
                        "",
                    ),
                    source_event_idempotency_key=idempotency_key,
                    content_entity_id=raw_event.get(
                        "content_entity_id"
                    ),
                )

                # --------------------------------------------------
                # Stage 3 — graph write
                # --------------------------------------------------

                graph_error: str | None = None

                if result.accepted_facts:

                    try:

                        graph_outcomes = await write_facts(
                            result.accepted_facts
                        )

                        logger.info(
                            "Graph write for %s: %s fact(s) written",
                            idempotency_key,
                            len(graph_outcomes),
                        )

                    except Exception as e:

                        graph_error = (
                            f"graph_write_failed: {e}"
                        )

                        logger.error(
                            "Graph write failed for %s: %s",
                            idempotency_key,
                            e,
                        )

                # --------------------------------------------------
                # Durable PostgreSQL status
                # --------------------------------------------------

                if idempotency_key:

                    await mark_processed(
                        db,
                        idempotency_key=idempotency_key,
                        error_message=graph_error,
                    )

                # --------------------------------------------------
                # Determine processing result
                # --------------------------------------------------

                success = graph_error is None

                processing_success[index] = success

                results.append(result)

                if success:

                    logger.info(
                        "Processed event %s: %s facts accepted, "
                        "%s rejection reasons",
                        idempotency_key,
                        len(result.accepted_facts),
                        len(result.rejected_reasons),
                    )

                else:

                    logger.warning(
                        "Event %s completed extraction but graph "
                        "processing failed; Kafka message will be "
                        "redelivered.",
                        idempotency_key,
                    )

            except Exception as e:

                processing_success[index] = False

                logger.exception(
                    "Unexpected processing failure for %s",
                    idempotency_key,
                )

                # --------------------------------------------------
                # Record failure in PostgreSQL.
                # --------------------------------------------------

                if idempotency_key:

                    try:

                        await mark_processed(
                            db,
                            idempotency_key=idempotency_key,
                            error_message=(
                                f"processing_failed: {e}"
                            ),
                        )

                    except Exception:

                        logger.exception(
                            "Failed to record processing failure "
                            "for %s",
                            idempotency_key,
                        )

    # --------------------------------------------------------------
    # Determine SAFE events for Kafka commit.
    #
    # We cannot simply commit every successful event.
    #
    # Example:
    #
    #   offset 100 → success
    #   offset 101 → failure
    #   offset 102 → success
    #
    # Safe commit:
    #
    #   offset 101
    #
    # NOT:
    #
    #   offset 103
    #
    # because committing 103 would skip offset 101.
    # --------------------------------------------------------------

    safe_events: list[ConsumedEvent] = []

    # Group events by partition.

    partition_events: dict[
        tuple[str, int],
        list[tuple[int, ConsumedEvent]],
    ] = {}

    for index, consumed_event in enumerate(consumed_events):

        if (
            consumed_event.topic is None
            or consumed_event.partition is None
            or consumed_event.offset is None
        ):
            # Fallback events have no Kafka metadata.
            # They don't participate in Kafka offset commits.
            continue

        partition_key = (
            consumed_event.topic,
            consumed_event.partition,
        )

        partition_events.setdefault(
            partition_key,
            [],
        ).append(
            (index, consumed_event)
        )

    # Find the contiguous successful prefix for every partition.

    for partition_key, events in partition_events.items():

        # Kafka messages are normally returned in offset order,
        # but sorting here makes the assumption explicit.

        events.sort(
            key=lambda item: item[1].offset
        )

        for index, consumed_event in events:

            if not processing_success.get(index, False):

                logger.warning(
                    "Stopping Kafka commit progression for "
                    "%s:%s at failed offset %s",
                    partition_key[0],
                    partition_key[1],
                    consumed_event.offset,
                )

                break

            safe_events.append(
                consumed_event
            )

    # --------------------------------------------------------------
    # Commit only the safe contiguous offsets.
    # --------------------------------------------------------------

    if safe_events:

        commit_success = await event_queue.commit(
            safe_events
        )

        if commit_success:

            logger.info(
                "Committed Redpanda offsets after processing "
                "%s safe event(s)",
                len(safe_events),
            )

        else:

            logger.error(
                "Redpanda offset commit failed after processing "
                "%s event(s). Events may be redelivered.",
                len(safe_events),
            )

    else:

        logger.info(
            "No safe Redpanda offsets to commit this iteration"
        )

    return results


async def run_processing_loop(
    interval_seconds: int = 10,
) -> None:
    """
    Background processing loop.

    Each iteration:

        1. Publish pending PostgreSQL outbox events.
        2. Consume Redpanda events.
        3. Run Stage 2 extraction.
        4. Run Stage 3 graph writes.
        5. Update PostgreSQL event status.
        6. Commit only safe contiguous Redpanda offsets.

    Runs until cancelled during application shutdown.
    """

    logger.info(
        "Background processing loop started "
        "(interval=%ss)",
        interval_seconds,
    )

    try:

        while True:

            try:

                # --------------------------------------------------
                # PostgreSQL outbox → Redpanda
                # --------------------------------------------------

                async with AsyncSessionLocal() as db:

                    await publish_pending(
                        db,
                        event_queue,
                    )

                # --------------------------------------------------
                # Redpanda → Stage 2 → Stage 3
                # --------------------------------------------------

                await process_pending_events()

            except Exception:

                logger.exception(
                    "Background processing loop iteration failed"
                )

            await asyncio.sleep(
                interval_seconds
            )

    except asyncio.CancelledError:

        logger.info(
            "Background processing loop stopped"
        )

        raise