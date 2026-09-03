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

# Install a CPU-only build of torch FIRST, from PyTorch's dedicated CPU
# wheel index, before installing the rest of requirements.txt.
#
# Why: on Linux, the default PyPI wheel for torch is the full GPU/CUDA
# build. This container has no GPU and only ever runs the local
# sentence-transformers embedding model on CPU -- but the default install
# still pulls nvidia-cudnn, nvidia-cusparselt, nvidia-nccl, nvidia-nvshmem,
# an entire bundled cuda-toolkit, and triton alongside it. That's several
# extra GB of downloads and build time for libraries that are never used,
# and it's why a plain `pip install -r requirements.txt` here can look
# like it's hanging on torch even though it's just working through a huge,
# unnecessary CUDA payload behind it.
#
# Installing the matching version from the CPU index here first means
# torch is already satisfied by the time `pip install -r requirements.txt`
# runs below, so pip sees the requirement is already met and skips
# reinstalling/re-resolving it from the default (GPU) index.
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model into the image so it's baked in, not
# fetched at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

# Alembic migrations, then the API. `sh -c` lets both commands run in
# sequence as the container's single startup step.
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]