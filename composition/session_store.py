"""
Stage 7 — Session Store (short-term conversational memory).

Backed by Valkey (Redis-API-compatible), which was already provisioned in
docker-compose.yml for "short-lived, subject-scoped caching" but not yet
wired up to any code. This is the first real usage of it.

Design:
- One Valkey key per session: "session:{session_id}"
- Value is a JSON-encoded list of {role, text} messages, oldest first
- TTL refreshed on every write, so active conversations stay alive and
  idle ones clean themselves up automatically — no manual cleanup job
- Deliberately NOT subject-scoped in the key itself: session_id is the
  isolation boundary here, matching Stage 7 Test C (session isolation)
"""

import json
import logging
import os

import redis

logger = logging.getLogger("composition.session_store")

_SESSION_TTL_SECONDS = 30 * 60  # 30 min idle expiry
_MAX_MESSAGES_STORED = 20  # cap raw history length; summarization is a later-stage concern

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        # .env only ever defines CACHE_URL (redis://host:port); VALKEY_HOST /
        # VALKEY_PORT aren't set anywhere. This only "worked" before because
        # their hardcoded defaults happened to match docker-compose's local
        # port mapping — it would silently point at the wrong host in any
        # environment where CACHE_URL was actually customized. Parse
        # CACHE_URL when present and fall back to the same defaults
        # otherwise, so this stays correct if the cache ever moves.
        cache_url = os.getenv("CACHE_URL")
        if cache_url:
            _client = redis.Redis.from_url(cache_url, decode_responses=True)
        else:
            _client = redis.Redis(
                host=os.getenv("VALKEY_HOST", "localhost"),
                port=int(os.getenv("VALKEY_PORT", "6379")),
                decode_responses=True,
            )
    return _client


def _key(session_id: str) -> str:
    return f"session:{session_id}"


def get_recent_messages(session_id: str) -> list[dict]:
    """Return this session's message history, oldest first. Empty list if none/expired."""
    client = get_client()
    try:
        raw = client.get(_key(session_id))
    except redis.exceptions.RedisError:
        logger.warning(
            "Session cache unavailable; continuing without conversation history"
        )
        return []

    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Corrupt session data for {session_id}, discarding")
        return []


def append_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    """
    Append one full turn (user message + assistant reply) to the session,
    trim to the most recent _MAX_MESSAGES_STORED messages, and refresh TTL.
    """
    client = get_client()
    messages = get_recent_messages(session_id)
    messages.append({"role": "user", "text": user_text})
    messages.append({"role": "assistant", "text": assistant_text})
    messages = messages[-_MAX_MESSAGES_STORED:]

    try:
        client.set(_key(session_id), json.dumps(messages), ex=_SESSION_TTL_SECONDS)
    except redis.exceptions.RedisError:
        logger.warning(
            "Session cache unavailable; response was returned without storing history"
        )


def format_conversation_history(messages: list[dict]) -> str:
    """Render session messages as plain text for the LLM prompt."""
    if not messages:
        return "No prior messages in this conversation."

    lines = []
    for m in messages:
        speaker = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {m['text']}")
    return "\n".join(lines)