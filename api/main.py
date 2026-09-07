"""
Main FastAPI application.

Run with:
    uvicorn api.main:app --reload

Application wiring:
    - Authentication
    - Ingestion
    - Retrieval
    - Chat / Composition
    - Background outbox publishing + processing
    - Neo4j constraints + vector index
"""

from __future__ import annotations

# IMPORTANT:
# Load .env BEFORE importing application modules that read environment
# variables at module-import time (especially auth.security).
from dotenv import load_dotenv

load_dotenv(override=True)

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from auth.api import router as auth_router
from auth.dependencies import get_current_user
from composition.api import router as chat_router
from database.connection import AsyncSessionLocal, close_database
from database.models import User
from database.outbox import publish_pending
from graph.writer import (
    close_driver,
    init_constraints,
    init_vector_index,
)
from ingestion.api import router as ingestion_router
from ingestion.queue import event_queue
from processing.consumer import (
    process_pending_events,
    run_processing_loop,
)

# Operational/debug endpoints (/debug/queue, /process/run) are gated by this
# flag in ADDITION to authentication. Default is off, so a production
# deployment doesn't expose them just because an env var was forgotten —
# they must be deliberately opted into (e.g. in a dev/staging .env).
ENABLE_DEBUG_ENDPOINTS = (
    os.getenv("ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true"
)
from retrieval.api import router as retrieval_router


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("api.main")


# ---------------------------------------------------------------------------
# APPLICATION LIFESPAN
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup/shutdown lifecycle.

    Startup:
        1. Start Redpanda/event queue.
        2. Ensure Neo4j constraints.
        3. Ensure Neo4j vector index.
        4. Start background processing loop.

    Shutdown:
        1. Stop background processing loop.
        2. Close Neo4j.
        3. Stop event queue.
        4. Close PostgreSQL.
    """

    processing_task: asyncio.Task | None = None

    try:
        # ---------------------------------------------------------------
        # STARTUP
        # ---------------------------------------------------------------

        logger.info("Starting Personalized AI Memory System")

        await event_queue.start()

        logger.info("Event queue started")

        await init_constraints()

        logger.info("Neo4j constraints ready")

        await init_vector_index()

        logger.info("Neo4j vector index ready")

        # Background publisher + processor.
        processing_task = asyncio.create_task(
            run_processing_loop()
        )

        logger.info("Background processing loop started")

        yield

    finally:
        # ---------------------------------------------------------------
        # SHUTDOWN
        # ---------------------------------------------------------------

        logger.info("Shutting down Personalized AI Memory System")

        if processing_task is not None:
            processing_task.cancel()

            try:
                await processing_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Background processing loop failed during shutdown"
                )

        try:
            await close_driver()
        except Exception:
            logger.exception("Error closing Neo4j driver")

        try:
            await event_queue.stop()
        except Exception:
            logger.exception("Error stopping event queue")

        try:
            await close_database()
        except Exception:
            logger.exception("Error closing PostgreSQL")

        logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# FASTAPI APPLICATION
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Personalized AI Memory System",
    description=(
        "Governed memory layer for AI-enabled Spotify surfaces"
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
#
# The frontend (Next.js) runs on a different origin than this API in every
# real deployment — localhost:3000 in dev, a vercel.app / custom domain in
# production — so without this, the browser blocks every request before it
# even reaches these routes, regardless of whether the frontend code is
# correct. FRONTEND_ORIGINS is a comma-separated list so local + staging +
# prod can all be allowed without a code change.
_frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------------------------

app.include_router(ingestion_router)
app.include_router(retrieval_router)
app.include_router(chat_router)
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """
    Basic liveness check.

    This endpoint intentionally does not require authentication so
    deployment/load-balancer health checks can access it.
    """
    return {
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# DEBUG QUEUE
# ---------------------------------------------------------------------------

@app.get("/debug/queue")
async def debug_queue(
    current_user: User = Depends(get_current_user),
):
    """
    Development-only endpoint for inspecting the fallback queue.

    Protected two ways:
      1. Requires a valid bearer token (same auth as /chat).
      2. Only registered/reachable when ENABLE_DEBUG_ENDPOINTS=true, so a
         production deployment doesn't expose it unless explicitly opted
         into (e.g. dev/staging .env). Leave unset/false in production.
    """

    if not ENABLE_DEBUG_ENDPOINTS:
        raise HTTPException(
            status_code=404,
            detail="Not found.",
        )

    return {
        "queued_events": event_queue.fallback_queue_contents(),
    }


# ---------------------------------------------------------------------------
# MANUAL PROCESSING TRIGGER
# ---------------------------------------------------------------------------

@app.post("/process/run")
async def run_processing(
    max_events: int = 50,
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger Stage 2 processing.

    The background processing loop normally handles this automatically.
    This endpoint remains useful for development, diagnostics, and
    controlled processing runs.

    Protected the same way as /debug/queue: requires authentication AND
    ENABLE_DEBUG_ENDPOINTS=true. An authenticated-but-untrusted caller
    should not be able to force off-cycle processing runs in production.
    """

    if not ENABLE_DEBUG_ENDPOINTS:
        raise HTTPException(
            status_code=404,
            detail="Not found.",
        )

    async with AsyncSessionLocal() as db:

        # First publish any durable outbox events that are waiting.
        await publish_pending(
            db,
            event_queue,
        )

    # Then process events that have reached the queue.
    results = await process_pending_events(
        max_events=max_events,
    )

    return {
        "processed_count": len(results),
        "results": [
            result.model_dump()
            for result in results
        ],
    }