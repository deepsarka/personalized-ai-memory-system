# Personalized AI Memory System — Spotify

A governed, event-driven memory layer for AI-enabled Spotify surfaces (conversational
assistance, playlist curation, podcast discovery). Facts are captured from interactions,
written to a temporal knowledge graph, retrieved by semantic + subject-scoped search, and
composed into bounded, policy-filtered context for an LLM — with correction, deletion, and
full audit trails as first-class operations, per the governed-memory brief this project
implements.

## Status

✅ **Feature-complete and deploy-ready.** All 8 pipeline stages (capture → extract →
graph-write → embed → retrieve → rerank/govern → compose → generate/observe) are
implemented and wired end to end, with authentication, a transactional outbox for durable
event delivery, short-term (Valkey) and long-term (Neo4j) memory both verified working, a
Streamlit frontend, and an MCP tool interface.

## Architecture

```
AI surface (chat/Streamlit)
   |
   v
POST /chat  --------------> PostgreSQL (interaction_events, outbox)
   |                              |
   |                     outbox publisher (claim/lease, exp. backoff)
   |                              v
   |                          Redpanda (durable transport)
   |                              |
   |                     Stage 2 consumer (idempotent)
   |                              v
   |                   Gemini extraction -> typed candidate facts
   |                              v
   |                    Neo4j temporal graph (Stage 3)
   |                    facts + embeddings (all-MiniLM-L6-v2)
   |                              |
   v                              v
Valkey (short-term          Neo4j vector index + subject
session cache, TTL)         isolation + temporal filter (Stage 4-5)
   |                              |
   +--------------+---------------+
                  v
       Reranking -> Governance -> Context composition (Stage 6)
                  v
            Gemini generation
                  v
       PostgreSQL observation + feedback (Stage 8)
```

**PostgreSQL and Neo4j are deliberately separate and do not overlap:**
- **PostgreSQL** — durable operational store only: users/auth, the interaction-event
  outbox (`accepted -> publishing -> published -> processed/failed`, with lease-based retry),
  and per-response observations/feedback. No memory facts live here.
- **Neo4j** — derived long-term memory only: `Subject`/`Fact` nodes with temporal validity
  (`valid_from`/`valid_until`), a cosine-similarity vector index for semantic retrieval, and
  idempotent `MERGE` writes so corrections supersede rather than silently overwrite facts.
- **Valkey** — short-term memory only: per-session conversation turns, 30-minute idle TTL,
  capped history length. Session-scoped, not a memory-fact store.

## Stack

| Layer | Tool |
|---|---|
| Backend/API | FastAPI + Pydantic, async (SQLAlchemy 2.0 + asyncpg) |
| Auth | JWT (PyJWT) + Argon2 password hashing (pwdlib) |
| Event transport | Redpanda (Kafka-API compatible), at-least-once, transactional outbox |
| Long-term memory | Neo4j Community Edition — temporal graph + built-in vector index |
| Short-term memory | Valkey (Redis-compatible), session-scoped, TTL'd |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2`, local, no external API |
| Operational store | PostgreSQL 16, migrated with Alembic |
| LLM (extraction + chat) | Google Gemini (`gemini-3.5-flash-lite`) |
| Tool interface | Model Context Protocol (MCP) SDK — `search_memory`, `chat`, `get_observation_tool`, `submit_feedback` |
| Frontend | Streamlit |
| Observability | LangSmith (optional, for LLM tracing) |

## Project structure

```
/auth           - registration, login, JWT issuance, get_current_user dependency
/ingestion      - Stage 1: event capture, schema validation, consent/identity checks
/database       - PostgreSQL models, connection, transactional outbox (source of truth)
/processing     - Stage 2: Gemini-based extraction, typed candidate facts, consumer loop
/graph          - Stage 3-4: Neo4j temporal writer, constraints, vector index, embeddings
/retrieval      - Stage 4-5: query embedding, subject-scoped hybrid retrieval, service layer
/composition    - Stage 6-7: reranking, governance/policy filtering, context composition,
                  session store (Valkey), chat service, chat API
/observation    - Stage 8: per-response observation + feedback (PostgreSQL)
/guardrails     - prompt-injection / leak-pattern input & output filtering
/mcp_server     - MCP tool interface over the same services used by the HTTP API
/frontend       - Streamlit UI (register/login, chat, memory inspection)
/alembic        - PostgreSQL schema migrations
/tests          - unit + integration tests (Neo4j-backed retrieval tests included)
/api            - FastAPI app wiring: routers, lifespan startup, background loops
```

## Local setup

1. **Start the data layer:**
   ```bash
   docker compose up -d neo4j redpanda postgres valkey
   ```
   Verify:
   - Neo4j browser: http://localhost:7474 (login: `neo4j` / `testpassword123`)
   - `docker compose ps` — services should show healthy/running

2. **Python environment** (backend needs `torch`/`sentence-transformers`, so this is a
   larger install):
   ```bash
   python3 -m venv venv
   source venv/bin/activate       # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
<<<<<<< HEAD
   # then fill in your gemini_model_api
=======
   # then fill in GEMINI_API_KEY and a real JWT_SECRET (32+ bytes -- see the
   # generation command in .env.example)
>>>>>>> 66477d7 (Prepare project for deployment)
   ```

4. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Run the API:**
   ```bash
   uvicorn api.main:app --reload
   ```
   Docs at http://localhost:8000/docs

6. **Run the frontend** (separate terminal, same venv):
   ```bash
   cd frontend
   streamlit run app.py
   ```
   Open http://localhost:8501 — register a user, then chat. The chat pipeline writes to
   Postgres immediately and to Neo4j asynchronously (via the background processing loop),
   so a fact you state may take a few seconds to become retrievable.

7. **Run tests** (needs the data layer running, esp. Neo4j on `bolt://localhost:7687` with
   password `testpassword123`, matching `docker-compose.yml`):
   ```bash
   pytest
   ```

## Deployment guide

You said you've already pushed the code to GitHub — here's how to take it from there.
Everything below assumes the fixes already applied in this repo (see "What was fixed"),
so no architecture changes are needed on your end.

### Option A — single VPS/VM with Docker Compose (simplest, recommended first deploy)

This runs the whole stack (data layer + API + frontend) on one machine via the
`docker-compose.yml` in this repo, which now includes `api` and `frontend` services in
addition to the four data-layer services.

1. **Provision a host.** Any VM with Docker + Docker Compose installed works (DigitalOcean
   Droplet, Hetzner, EC2, Lightsail, etc.). Given `torch`/`sentence-transformers` in the
   image, 2 vCPU / 4GB RAM is a reasonable minimum.

2. **Clone your repo on the host:**
   ```bash
   git clone <your-repo-url>
   cd <repo>
   ```

3. **Create `.env` on the host** — copy `.env.example`, fill in `GEMINI_API_KEY` and a
   real `JWT_SECRET`. Leave `ENABLE_DEBUG_ENDPOINTS=false`. You do **not** need to change
   `NEO4J_URI`/`POSTGRES_URL`/`CACHE_URL`/`REDPANDA_BOOTSTRAP_SERVERS` — the `api` service
   in `docker-compose.yml` overrides those to the in-network container names
   (`neo4j`, `postgres`, `valkey`, `redpanda`) automatically.

4. **Build and start everything:**
   ```bash
   docker compose up -d --build
   ```
   The `api` container runs `alembic upgrade head` automatically before starting uvicorn
   (see `Dockerfile`), so PostgreSQL tables are created on first boot.

5. **Verify:**
   ```bash
   docker compose ps                      # everything healthy/running
   curl http://localhost:8000/health      # {"status": "ok"}
   ```
   Frontend is on port `8501`, API on `8000`. Put a reverse proxy (Caddy, nginx, or your
   cloud provider's load balancer) in front for HTTPS/TLS and a real domain — none of the
   containers terminate TLS themselves.

6. **Point the frontend at the right API URL if you split hosts later.** As shipped, the
   `frontend` service already points at `http://api:8000` (in-network). If you ever run the
   frontend on a different host, set `API_BASE_URL` to the API's public HTTPS URL instead.

### Option B — split deployment (managed platforms)

If you'd rather use managed services instead of self-hosting the data layer on your VM:

- **Neo4j** → Neo4j AuraDB (free tier exists) instead of the `neo4j` container.
- **PostgreSQL** → any managed Postgres (Railway, Render, Supabase, RDS).
- **Redpanda** → Redpanda Cloud, or a managed Kafka if you'd rather (the code only needs a
  Kafka-API-compatible broker).
- **Valkey/Redis** → any managed Redis-compatible cache.
- **API** → deploy the root `Dockerfile` to Render/Railway/Fly.io/ECS, set env vars to the
  managed services' connection strings.
- **Frontend** → same platform or a separate one; set `API_BASE_URL` to the API's public URL.

This avoids running stateful services yourself, at the cost of a few more accounts/configs
to wire up. Nothing in the codebase needs to change either way — it's all environment
variables.

### Before you deploy — checklist

- [ ] `JWT_SECRET` in production `.env` is a real random 32+ byte value, not the example.
- [ ] `GEMINI_API_KEY` is set.
- [ ] `ENABLE_DEBUG_ENDPOINTS` is `false` (or unset) in production — this gates
      `/debug/queue` and `/process/run`, which are also now behind authentication.
- [ ] `ALLOW_IN_MEMORY_FALLBACK` is `false` in production — you want Redpanda publish
      failures to surface (and retry via the outbox), not silently vanish into an
      in-process fallback queue that's lost on restart.
- [ ] A reverse proxy handles HTTPS in front of the API/frontend ports.
- [ ] Postgres/Neo4j volumes are backed up if you're self-hosting them (Option A) — the
      `docker-compose.yml` volumes (`neo4j_data`, `postgres_data`) are local to the host
      and won't survive a host loss on their own.

## What was fixed in this pass

1. **Long-term (Neo4j) memory retrieval was returning nothing.** Facts are written to
   Neo4j with `valid_from`/`valid_until` stored as ISO strings, but the retrieval query
   was filtering with `node.valid_from <= datetime()` — comparing a String to Cypher's
   native DateTime type, which evaluates to `null` and silently drops every row from the
   `WHERE` clause. Fixed by comparing against a same-format ISO string instead
   (`retrieval/retriever.py`). Session (Valkey) memory was unaffected since it never went
   through this query — which is why only long-term memory looked broken.
2. Added `tests/test_stage5_retrieval.py` (previously an empty file) — write-then-retrieve
   integration tests against real Neo4j, including expired/future-fact filtering, so this
   class of bug fails a test instead of failing silently in production.
3. `/debug/queue` and `/process/run` now require authentication and are only reachable at
   all when `ENABLE_DEBUG_ENDPOINTS=true` (default `false`).
4. `requirements.txt` contained `pywin32`, a Windows-only package that would fail to
   install on any Linux deploy target — removed. The file was also UTF-16 encoded with
   CRLF line endings (from a Windows `pip freeze`); normalized to UTF-8/LF.
5. `.env.example` didn't exist even though the README told people to copy it — added,
   matching the real `.env` keys (this project uses Gemini, not the Anthropic API the old
   README described).
6. The Streamlit frontend hardcoded `http://127.0.0.1:8000` as the API URL, which breaks
   as soon as frontend and backend run on separate hosts/containers. Now reads
   `API_BASE_URL` (env var), defaulting to localhost for local dev.
7. Added `Dockerfile` (backend) and `frontend/Dockerfile`, wired into `docker-compose.yml`
   as `api` and `frontend` services, so `docker compose up -d --build` deploys the whole
   stack. The backend image pre-downloads the local embedding model at build time so
   containers don't depend on reaching Hugging Face Hub at runtime.
8. Added `.dockerignore` so the local `venv/` (1.5GB) isn't copied into build contexts.

None of this changed the architecture from the original design — PostgreSQL and Neo4j
remain separate as specified, and the fixes are all bugs or deployment gaps, not design
changes.


