# Backend API — FastAPI app (ingestion, retrieval, chat/composition, MCP server).
#
# Bakes the local sentence-transformers embedding model into the image at
# build time (graph/embeddings.py and retrieval/embedding.py both lazily
# download all-MiniLM-L6-v2 from Hugging Face Hub on first use otherwise,
# which means the container's first request would silently depend on
# outbound network access to huggingface.co — this avoids that dependency
# in production).
FROM python:3.12-slim AS base

WORKDIR /app

# Build deps for packages with native extensions (cryptography, etc.),
# removed from the final layer by using a single RUN with cleanup.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model into the image so it's baked in, not
# fetched at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

# Alembic migrations, then the API. `sh -c` lets both commands run in
# sequence as the container's single startup step.
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
