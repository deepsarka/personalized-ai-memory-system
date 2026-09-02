"""
Retrieval API router — Stage 5.

Exposes the working RetrievalService (proven locally via test_stage5.py)
as a live HTTP endpoint so the API/LLM layer can query memories at runtime.
"""

import os
import logging

from fastapi import APIRouter, HTTPException

from retrieval.service import RetrievalService
from retrieval.retrieval_models import RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])

# Single shared service instance, built from the same env vars
# used elsewhere in the app (graph.writer / docker-compose).
_service: RetrievalService | None = None


def get_service() -> RetrievalService:
    global _service
    if _service is None:
        _service = RetrievalService(
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "testpassword123"),
        )
    return _service


@router.post("/query", response_model=RetrievalResult)
async def query_memories(request: RetrievalQuery) -> RetrievalResult:
    """
    Stage 5 — live retrieval.

    Accepts a subject_id + natural language query, embeds the query,
    performs vector search against Neo4j-stored facts, and returns
    the top_k most relevant, currently-valid facts for that subject.
    """
    try:
        service = get_service()
        result = service.retrieve(request)
        return result
    except Exception as e:
        logger.exception("Retrieval failed for subject_id=%s", request.subject_id)
        raise HTTPException(status_code=500, detail=str(e))