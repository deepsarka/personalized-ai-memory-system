"""
MCP Server — Personalized AI Memory System.

Exposes the existing memory system through MCP tools.

Architecture:

MCP Client
    ->
MCP Server
    ->
Existing Stage 5/6/7/8 services
    ->
Neo4j / Valkey / PostgreSQL / Gemini
"""

import os
import uuid

from mcp.server.fastmcp import FastMCP

from retrieval.service import RetrievalService
from retrieval.retrieval_models import RetrievalQuery

from composition.chat_service import ChatService

from observation.feedback import FeedbackService
from observation.store import get_observation


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP("Spotify Personalized AI Memory")


# ============================================================
# SHARED SERVICES
# ============================================================

_retrieval_service: RetrievalService | None = None
_chat_service: ChatService | None = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service

    if _retrieval_service is None:
        _retrieval_service = RetrievalService(
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

    return _retrieval_service


def get_chat_service() -> ChatService:
    global _chat_service

    if _chat_service is None:
        _chat_service = ChatService(
            retrieval_service=get_retrieval_service()
        )

    return _chat_service


# ============================================================
# TOOL 1 — SEARCH MEMORY
# ============================================================

@mcp.tool()
def search_memory(
    subject_id: str,
    query: str,
    top_k: int = 5,
) -> dict:
    """
    Search the user's long-term memory.

    Uses the existing Stage 5 RetrievalService:
        query
        ->
        embedding
        ->
        Neo4j vector search
        ->
        subject isolation
        ->
        currently valid memories

    Args:
        subject_id: User/subject whose memories should be searched.
        query: Natural-language memory search query.
        top_k: Maximum number of memories to return.
    """

    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")

    service = get_retrieval_service()

    result = service.retrieve(
        RetrievalQuery(
            subject_id=subject_id,
            query=query,
            top_k=top_k,
        )
    )

    return result.model_dump(mode="json")


# ============================================================
# TOOL 2 — CHAT
# ============================================================

@mcp.tool()
def chat(
    subject_id: str,
    query: str,
    session_id: str | None = None,
    top_k: int = 5,
) -> dict:
    """
    Generate a personalized response using the complete memory pipeline.

    Pipeline:

        Retrieval
            ->
        Reranking
            ->
        Governance
            ->
        Memory Composition
            ->
        Context Builder
            ->
        Valkey conversation history
            ->
        Gemini
            ->
        Observation in PostgreSQL

    Args:
        subject_id: User/subject identifier.
        query: Current user request.
        session_id: Existing conversation session ID, if available.
        top_k: Number of governed memories to use.
    """

    session_id = session_id or str(uuid.uuid4())

    service = get_chat_service()

    return service.respond(
        subject_id=subject_id,
        query=query,
        session_id=session_id,
        top_k=top_k,
    )


# ============================================================
# TOOL 3 — GET OBSERVATION
# ============================================================

@mcp.tool()
def get_observation_tool(
    request_id: str,
) -> dict:
    """
    Retrieve an observation recorded for a generated response.

    Observations are stored in PostgreSQL.

    Args:
        request_id: Request ID returned by the chat tool.
    """

    record = get_observation(request_id)

    if record is None:
        return {
            "found": False,
            "request_id": request_id,
        }

    return {
        "found": True,
        "request_id": record.request_id,
        "session_id": record.session_id,
        "subject_id": record.subject_id,
        "timestamp": record.timestamp.isoformat(),
        "retrieved_memory_ids": record.retrieved_memory_ids,
        "model": record.model,
        "latency_ms": record.latency_ms,
        "fallback_used": record.fallback_used,
        "response_text": record.response_text,
        "feedback_id": record.feedback_id,
        "feedback": record.feedback,
    }


# ============================================================
# TOOL 4 — SUBMIT FEEDBACK
# ============================================================

@mcp.tool()
def submit_feedback(
    request_id: str,
    feedback: str,
) -> dict:
    """
    Attach user feedback to an existing chat observation.

    Valid feedback:
        positive
        negative

    Args:
        request_id: Request ID returned by chat().
        feedback: User feedback, either positive or negative.
    """

    service = FeedbackService()

    return service.submit_feedback(
        request_id=request_id,
        feedback=feedback,
    )


# ============================================================
# SERVER ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    mcp.run()