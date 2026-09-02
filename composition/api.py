
"""
Stage 6 + 7 + 8.1 + 8.3 — Chat API router.

Exposes:
    POST /chat
        Full Stage 6 + 7 pipeline.
        The interaction is durably recorded in PostgreSQL first.
        The transactional outbox publisher is responsible for Redpanda.

    GET /chat/observation/{request_id}
        Inspect stored observation and feedback.

    POST /chat/feedback
        Submit positive/negative feedback for an observation.
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from composition.chat_service import ChatService
from database.connection import get_db
from database.models import User
from database.outbox import record_event_if_new
from observation.feedback import FeedbackService
from observation.store import get_observation
from retrieval.service import RetrievalService


logger = logging.getLogger("composition.api")

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """
    Lazily create the ChatService.

    Retrieval/Neo4j resources are initialized only when the first
    chat request arrives.
    """
    global _chat_service

    if _chat_service is None:
        retrieval_service = RetrievalService(
            neo4j_uri=os.getenv(
                "NEO4J_URI",
                "bolt://localhost:7687",
            ),
            neo4j_username=os.getenv(
                "NEO4J_USERNAME",
                "neo4j",
            ),
            neo4j_password=os.getenv(
                "NEO4J_PASSWORD",
                "testpassword123",
            ),
        )

        _chat_service = ChatService(
            retrieval_service=retrieval_service,
        )

    return _chat_service


class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    session_id: str | None = None

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    idempotency_key: str = Field(
        ...,
        min_length=8,
        max_length=255,
    )


class ChatResponse(BaseModel):
    request_id: str
    subject_id: str
    session_id: str
    query: str
    memory_context_used: str
    conversation_history_used: str
    facts_used: list[str]
    response: str


class ObservationResponse(BaseModel):
    request_id: str
    session_id: str | None
    subject_id: str
    timestamp: str
    retrieved_memory_ids: list[str]
    model: str
    latency_ms: int
    fallback_used: bool
    response_text: str | None
    feedback_id: str | None
    feedback: str | None


class FeedbackRequest(BaseModel):
    request_id: str
    feedback: str


class FeedbackResponse(BaseModel):
    feedback_id: str
    request_id: str
    feedback: str


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Process a chat request.

    IMPORTANT EVENT LIFECYCLE:

        HTTP /chat
            ↓
        PostgreSQL interaction_events
            ↓
        ACCEPTED
            ↓
        transactional outbox publisher
            ↓
        Redpanda
            ↓
        Stage 2 consumer
            ↓
        extraction / Neo4j

    The chat endpoint MUST NOT publish directly to Redpanda.

    This guarantees that an accepted chat interaction is durably
    recorded even if Redpanda is temporarily unavailable.
    """

    subject_id = str(current_user.id)

    session_id = request.session_id or str(uuid.uuid4())

    # Generate the event idempotency key once.
    #
    # This key is persisted in PostgreSQL and is the durable identity
    # of this interaction event.
    idempotency_key = request.idempotency_key

    now = datetime.now(timezone.utc)

    payload = {
        "subject_id": subject_id,
        "raw_text": request.query,
        "idempotency_key": idempotency_key,
        "event_type": "explicit_statement",
        "schema_version": "1.0",
        "service_id": "spotify-memory-system",
        "surface": "chat",
        "consent_state": "granted",
        "event_timestamp": now.isoformat(),
        "content_entity_id": None,
    }

    try:
        # --------------------------------------------------------------
        # P0: DURABLE EVENT RECORDING
        # --------------------------------------------------------------
        #
        # DO NOT call event_queue.publish() here.
        #
        # record_event_if_new() writes the interaction to PostgreSQL.
        # The background outbox publisher will later publish it to
        # Redpanda.
        #
        inserted = await record_event_if_new(
            session=db,
            idempotency_key=idempotency_key,
            subject_id=subject_id,
            schema_version="1.0",
            service_id="spotify-memory-system",
            surface="chat",
            event_type="explicit_statement",
            consent_state="granted",
            raw_text=request.query,
            content_entity_id=None,
            event_timestamp=now,
            payload=payload,
        )

        if not inserted:
            logger.warning(
                "Chat event already exists: "
                "subject_id=%s idempotency_key=%s",
                subject_id,
                idempotency_key,
            )

        # --------------------------------------------------------------
        # RESPONSE GENERATION
        # --------------------------------------------------------------
        #
        # This remains synchronous because the current ChatService API
        # is synchronous.
        #
        # The important architectural change is that event persistence
        # is completed before response generation.
        #
        service = get_chat_service()

        result = service.respond(
            subject_id=subject_id,
            query=request.query,
            session_id=session_id,
            top_k=request.top_k,
        )

        return ChatResponse(**result)

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Chat failed for subject_id=%s",
            subject_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Chat request could not be processed.",
        )


@router.get(
    "/observation/{request_id}",
    response_model=ObservationResponse,
)
async def get_chat_observation(
    request_id: str,
    current_user: User = Depends(get_current_user),
) -> ObservationResponse:
    """
    Inspect a stored observation.

    Authentication is required so an arbitrary user cannot inspect
    another user's observation by guessing a request_id.
    """

    record = get_observation(request_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No observation found for request_id={request_id}",
        )

    # Prevent cross-user observation access.
    if record.subject_id != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to access this observation.",
        )

    return ObservationResponse(
        request_id=record.request_id,
        session_id=record.session_id,
        subject_id=record.subject_id,
        timestamp=record.timestamp.isoformat(),
        retrieved_memory_ids=record.retrieved_memory_ids,
        model=record.model,
        latency_ms=record.latency_ms,
        fallback_used=record.fallback_used,
        response_text=record.response_text,
        feedback_id=record.feedback_id,
        feedback=record.feedback,
    )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """
    Submit feedback for an observation.

    Authentication is required before accepting feedback.
    """

    record = get_observation(request.request_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No observation found for "
                f"request_id={request.request_id}"
            ),
        )

    if record.subject_id != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to submit feedback for this observation.",
        )

    try:
        service = FeedbackService()

        result = service.submit_feedback(
            request_id=request.request_id,
            feedback=request.feedback,
        )

        return FeedbackResponse(**result)

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception:
        logger.exception(
            "Feedback submission failed for request_id=%s",
            request.request_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Feedback could not be submitted.",
        )

