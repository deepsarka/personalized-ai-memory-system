"""
Stage 8.1/8.3 — Observation store (Postgres).

Uses port 5433 by default -- port 5432 had a stale/conflicting binding on
this machine (confirmed via direct psycopg2 test), so the container was
remapped to 5433 in docker-compose.yml. Keep this in sync with .env's
POSTGRES_URL if that port ever changes again.
"""

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from observation.models import Base, ObservationRecord

logger = logging.getLogger("observation.store")

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal

    if _engine is None:
        url = os.getenv(
            "POSTGRES_URL",
            "postgresql+psycopg2://memory_admin:devpassword123@127.0.0.1:5433/memory_ops"
        )

        try:
            _engine = create_engine(url, pool_pre_ping=True)
            Base.metadata.create_all(_engine)
            _SessionLocal = sessionmaker(
                bind=_engine,
                expire_on_commit=False,
            )
            logger.info("Postgres observation store initialized (table ensured)")
        except Exception as e:
            logger.error(f"Failed to initialize Postgres observation store engine: {e}")
            _engine = None
            _SessionLocal = None
            raise

    return _engine


def _get_session() -> Session:
    _get_engine()
    if _SessionLocal is None:
        raise RuntimeError("Database session local factory is not initialized.")
    return _SessionLocal()


def save_observation(record: ObservationRecord) -> None:
    session = _get_session()
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(f"Failed to save observation {record.request_id}")
        raise
    finally:
        session.close()


def get_observation(request_id: str) -> ObservationRecord | None:
    session = _get_session()
    try:
        return (
            session.query(ObservationRecord)
            .filter(ObservationRecord.request_id == request_id)
            .first()
        )
    finally:
        session.close()


def update_feedback(request_id: str, feedback: str, feedback_id: str) -> bool:
    """
    Stage 8.3 — attach feedback to an existing observation row.
    Returns True if a row was found and updated, False if request_id
    doesn't correspond to any known observation.
    """
    session = _get_session()
    try:
        record = (
            session.query(ObservationRecord)
            .filter(ObservationRecord.request_id == request_id)
            .first()
        )
        if record is None:
            return False

        record.feedback = feedback
        record.feedback_id = feedback_id
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.exception(f"Failed to update feedback for {request_id}")
        raise
    finally:
        session.close()