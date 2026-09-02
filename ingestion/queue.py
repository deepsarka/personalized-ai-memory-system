"""
Durable event transport.

Architecture:

    PostgreSQL outbox
          |
          v
      Redpanda
          |
          v
       Consumer
          |
          v
    Stage 2 / Stage 3
          |
          v
   explicit offset commit

Delivery semantics:
    AT-LEAST-ONCE

Important:
    PostgreSQL is the durable source of truth.
    Redpanda is the transport.
    The in-memory fallback is development-only.

A Redpanda publish failure ALWAYS returns False.
It is NEVER converted into a successful publish.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ingestion.queue")


@dataclass(slots=True)
class ConsumedEvent:
    """Event plus Kafka metadata required for explicit commits."""

    event: dict[str, Any]

    topic: str | None = None
    partition: int | None = None
    offset: int | None = None


class EventQueue:
    """
    Redpanda/Kafka transport.

    The fallback queue exists only for local development/testing.

    Production behavior:
        Redpanda unavailable -> publish() returns False.
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        group_id: str | None = None,
    ) -> None:
        self.bootstrap_servers = (
            bootstrap_servers
            or os.getenv("REDPANDA_BOOTSTRAP_SERVERS", "localhost:9092")
        )

        self.topic = (
            topic
            or os.getenv(
                "REDPANDA_TOPIC",
                "interaction-events",
            )
        )

        self.group_id = (
            group_id
            or os.getenv(
                "REDPANDA_GROUP_ID",
                "stage2-processor",
            )
        )

        self.allow_fallback = (
            os.getenv(
                "ALLOW_IN_MEMORY_FALLBACK",
                "false",
            ).lower()
            == "true"
        )

        self._producer = None
        self._consumer = None

        self._fallback_queue: list[dict[str, Any]] = []

        self._use_fallback = False
        self._consumer_started = False
        self._producer_started = False

    # ==================================================================
    # STARTUP
    # ==================================================================

    async def start(self) -> None:
        """
        Start producer and consumer.

        Production:
            Redpanda failure causes startup failure.

        Development:
            Set ALLOW_IN_MEMORY_FALLBACK=true to enable fallback.
        """

        if self._producer_started or self._consumer_started:
            logger.debug("EventQueue already started")
            return

        try:
            from aiokafka import (
                AIOKafkaConsumer,
                AIOKafkaProducer,
            )

            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                acks="all",
                enable_idempotence=True,
                compression_type="gzip",
            )

            await producer.start()

            self._producer = producer
            self._producer_started = True

            logger.info(
                "Redpanda producer started: %s",
                self.bootstrap_servers,
            )

            consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
            )

            await consumer.start()

            self._consumer = consumer
            self._consumer_started = True

            self._use_fallback = False

            logger.info(
                "Redpanda consumer started: topic=%s group=%s",
                self.topic,
                self.group_id,
            )

        except Exception as exc:
            logger.exception(
                "Failed to start Redpanda transport: %s",
                exc,
            )

            await self._cleanup_partial_startup()

            if not self.allow_fallback:
                raise RuntimeError(
                    "Redpanda is unavailable and "
                    "ALLOW_IN_MEMORY_FALLBACK is false."
                ) from exc

            self._use_fallback = True

            logger.warning(
                "Using development-only in-memory fallback."
            )

    async def _cleanup_partial_startup(self) -> None:
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:
                logger.exception(
                    "Failed to stop partial consumer"
                )

        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:
                logger.exception(
                    "Failed to stop partial producer"
                )

        self._consumer = None
        self._producer = None

        self._consumer_started = False
        self._producer_started = False

    # ==================================================================
    # SHUTDOWN
    # ==================================================================

    async def stop(self) -> None:
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:
                logger.exception(
                    "Failed stopping Redpanda consumer"
                )
            finally:
                self._consumer = None
                self._consumer_started = False

        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:
                logger.exception(
                    "Failed stopping Redpanda producer"
                )
            finally:
                self._producer = None
                self._producer_started = False

        self._use_fallback = False

        logger.info("EventQueue stopped")

    # ==================================================================
    # PRODUCER
    # ==================================================================

    async def publish(
        self,
        event_dict: dict[str, Any],
    ) -> bool:
        """
        Publish an event.

        True:
            Redpanda acknowledged the message.

        False:
            Message was not durably acknowledged by Redpanda.

        IMPORTANT:
            False is required for PostgreSQL outbox retry semantics.
        """

        if not isinstance(event_dict, dict):
            raise TypeError(
                "event_dict must be a dictionary"
            )

        event_key = event_dict.get(
            "idempotency_key"
        )

        # --------------------------------------------------------------
        # Development fallback ONLY
        # --------------------------------------------------------------

        if self._use_fallback:
            if not self.allow_fallback:
                logger.error(
                    "Fallback mode active while fallback is disabled"
                )
                return False

            self._fallback_queue.append(
                dict(event_dict)
            )

            logger.warning(
                "[DEV FALLBACK] event queued: key=%s",
                event_key,
            )

            return True

        # --------------------------------------------------------------
        # No producer means publication did not happen.
        # --------------------------------------------------------------

        if self._producer is None or not self._producer_started:
            logger.error(
                "Redpanda producer unavailable: key=%s",
                event_key,
            )
            return False

        # --------------------------------------------------------------
        # Serialize
        # --------------------------------------------------------------

        try:
            payload = json.dumps(
                event_dict,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")

        except Exception:
            logger.exception(
                "Failed to serialize event: key=%s",
                event_key,
            )
            return False

        # --------------------------------------------------------------
        # Publish
        # --------------------------------------------------------------

        try:
            await self._producer.send_and_wait(
                self.topic,
                payload,
            )

            logger.debug(
                "Event published: key=%s",
                event_key,
            )

            return True

        except Exception:
            logger.exception(
                "Redpanda publish failed: key=%s",
                event_key,
            )

            # NEVER fallback here.
            #
            # PostgreSQL owns retry state.
            #
            # Returning False causes:
            #
            # PUBLISHING -> ACCEPTED

            return False

    # ==================================================================
    # CONSUMER
    # ==================================================================

    async def consume_available(
        self,
        max_events: int = 50,
        timeout_ms: int = 1000,
    ) -> list[ConsumedEvent]:

        if max_events <= 0:
            return []

        # --------------------------------------------------------------
        # Development fallback
        # --------------------------------------------------------------

        if self._use_fallback:
            return [
                ConsumedEvent(
                    event=event,
                )
                for event in self._fallback_queue[:max_events]
            ]

        if (
            self._consumer is None
            or not self._consumer_started
        ):
            logger.warning(
                "Redpanda consumer is not started"
            )
            return []

        consumed: list[ConsumedEvent] = []

        try:
            data = await self._consumer.getmany(
                timeout_ms=timeout_ms,
                max_records=max_events,
            )

            for topic_partition, messages in data.items():
                for msg in messages:
                    try:
                        raw_value = msg.value

                        if isinstance(raw_value, bytes):
                            raw_value = raw_value.decode(
                                "utf-8"
                            )

                        event = json.loads(
                            raw_value
                        )

                        if not isinstance(event, dict):
                            raise ValueError(
                                "Kafka event must be a JSON object"
                            )

                        consumed.append(
                            ConsumedEvent(
                                event=event,
                                topic=msg.topic,
                                partition=msg.partition,
                                offset=msg.offset,
                            )
                        )

                    except Exception:
                        logger.exception(
                            "Invalid Redpanda message: "
                            "topic=%s partition=%s offset=%s",
                            msg.topic,
                            msg.partition,
                            msg.offset,
                        )

                        # Do not commit malformed message.
                        #
                        # Later we will add DLQ handling.
                        continue

        except Exception:
            logger.exception(
                "Redpanda consume failed"
            )

        return consumed

    # ==================================================================
    # FALLBACK ACK
    # ==================================================================

    def acknowledge_fallback(
        self,
        event: dict[str, Any],
    ) -> bool:

        event_key = event.get(
            "idempotency_key"
        )

        for index, queued_event in enumerate(
            self._fallback_queue
        ):
            if (
                queued_event is event
                or (
                    event_key
                    and queued_event.get(
                        "idempotency_key"
                    )
                    == event_key
                )
            ):
                del self._fallback_queue[index]
                return True

        return False

    # ==================================================================
    # OFFSET COMMIT
    # ==================================================================

    async def commit(
        self,
        successful_events: list[ConsumedEvent],
    ) -> bool:

        if not successful_events:
            return True

        # --------------------------------------------------------------
        # Fallback
        # --------------------------------------------------------------

        if self._use_fallback:
            for event in successful_events:
                if (
                    event.topic is None
                    and event.partition is None
                    and event.offset is None
                ):
                    self.acknowledge_fallback(
                        event.event
                    )

            return True

        if (
            self._consumer is None
            or not self._consumer_started
        ):
            logger.error(
                "Cannot commit offsets: consumer unavailable"
            )
            return False

        try:
            from aiokafka.structs import (
                OffsetAndMetadata,
                TopicPartition,
            )

            partition_events: dict[
                TopicPartition,
                list[ConsumedEvent],
            ] = {}

            for event in successful_events:

                if (
                    event.topic is None
                    or event.partition is None
                    or event.offset is None
                ):
                    logger.warning(
                        "Skipping event with missing Kafka metadata"
                    )
                    continue

                tp = TopicPartition(
                    event.topic,
                    event.partition,
                )

                partition_events.setdefault(
                    tp,
                    [],
                ).append(event)

            if not partition_events:
                return True

            offsets: dict[
                TopicPartition,
                OffsetAndMetadata,
            ] = {}

            for tp, events in partition_events.items():

                events.sort(
                    key=lambda e: e.offset
                )

                expected = events[0].offset

                for event in events:

                    if event.offset != expected:
                        logger.error(
                            "Unsafe Kafka commit refused: "
                            "%s:%s expected=%s got=%s",
                            tp.topic,
                            tp.partition,
                            expected,
                            event.offset,
                        )
                        return False

                    expected += 1

                offsets[tp] = OffsetAndMetadata(
                    expected,
                    "",
                )

            await self._consumer.commit(
                offsets=offsets
            )

            logger.info(
                "Redpanda offsets committed: %s",
                {
                    f"{tp.topic}:{tp.partition}":
                    metadata.offset
                    for tp, metadata in offsets.items()
                },
            )

            return True

        except Exception:
            logger.exception(
                "Redpanda offset commit failed"
            )
            return False

    # ==================================================================
    # DEBUG / TEST
    # ==================================================================

    def fallback_queue_contents(
        self,
    ) -> list[dict[str, Any]]:

        return [
            dict(event)
            for event in self._fallback_queue
        ]


event_queue = EventQueue()