"""
Stage 4 — local embedding model wrapper.

Uses sentence-transformers (already in requirements.txt) running locally —
no API key, no rate limit, no network call, fully deterministic. This is
deliberate: Stage 2 already burned real time on Anthropic billing and
Gemini rate limits, so embeddings — which run once per fact, not
interactively — are a good place to avoid a third external API dependency.

Model: all-MiniLM-L6-v2 — small (~80MB), fast on CPU, 384 dimensions. Not a
frontier embedding model, but this is a single-user-scoped memory store
with a handful of facts per subject, not a billion-vector search problem —
quality here is not the bottleneck.
"""

import logging
from functools import lru_cache

logger = logging.getLogger("graph.embeddings")

EMBEDDING_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading local embedding model ({_MODEL_NAME})... first call only, may take a moment")
    return SentenceTransformer(_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """
    Embed a single string. Returns a 384-dim float list, ready to store as
    a Neo4j node property and query against the vector index.
    """
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)  # normalized so cosine similarity is well-behaved
    return vector.tolist()
