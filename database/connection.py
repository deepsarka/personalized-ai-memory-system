"""
PostgreSQL application database connection.

Uses SQLAlchemy's async engine for FastAPI request/worker paths.

PostgreSQL is the durable source of truth for application data.
Neo4j remains the derived graph/semantic memory store.
"""

import logging
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()

logger = logging.getLogger("database.connection")


POSTGRES_URL = os.getenv("POSTGRES_URL")

if not POSTGRES_URL:
    raise RuntimeError(
        "POSTGRES_URL is not set. Copy .env.example to .env and set it "
        "(see docker-compose.yml for the local dev value) before starting "
        "the app."
    )


def _to_async_url(url: str) -> str:
    """
    Normalize PostgreSQL URLs to the asyncpg SQLAlchemy dialect.

    Supported:
        postgresql+asyncpg://
        postgresql+psycopg2://
        postgresql://
        postgres://
    """

    if url.startswith("postgresql+asyncpg://"):
        return url

    if url.startswith("postgresql+psycopg2://"):
        return url.replace(
            "postgresql+psycopg2://",
            "postgresql+asyncpg://",
            1,
        )

    if url.startswith("postgresql://"):
        return url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )

    if url.startswith("postgres://"):
        return url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )

    return url


ASYNC_POSTGRES_URL = _to_async_url(POSTGRES_URL)


engine = create_async_engine(
    ASYNC_POSTGRES_URL,
    pool_pre_ping=True,
    pool_recycle=int(
        os.getenv("POSTGRES_POOL_RECYCLE", "1800")
    ),
    pool_size=int(
        os.getenv("POSTGRES_POOL_SIZE", "10")
    ),
    max_overflow=int(
        os.getenv("POSTGRES_MAX_OVERFLOW", "20")
    ),
    echo=os.getenv(
        "POSTGRES_ECHO",
        "false",
    ).lower() == "true",
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency providing one AsyncSession per request.

    The request transaction is committed when the endpoint succeeds
    and rolled back when the endpoint raises an exception.

    Individual service functions that explicitly own a transaction may
    commit their own transaction; SQLAlchemy safely starts a new
    transaction when required afterward.
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()

        except Exception:
            await session.rollback()
            raise


async def close_database() -> None:
    """
    Dispose the PostgreSQL connection pool during application shutdown.
    """

    await engine.dispose()

    logger.info(
        "PostgreSQL connection pool closed"
    )