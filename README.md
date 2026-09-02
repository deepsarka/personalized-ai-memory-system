# Personalized AI Memory System — Prototype

A governed memory layer for AI-enabled Spotify surfaces (discovery, playlist curation,
podcast exploration, conversational assistance). Built for Applied GenAI Engineering
course completion.

## Architecture

Follows the 6-stage lifecycle: **Capture → Normalize/Resolve → Write Temporal Memory →
Retrieve for Intent → Filter/Compose → Generate/Explain/Learn**

See `/report` for the full design doc, governance model, and user-journey mapping.

## Stack (all free, self-hosted)

| Layer | Tool |
|---|---|
| Backend/API | FastAPI + Pydantic |
| Event transport | Redpanda (Kafka-compatible) |
| Graph memory | Neo4j Community Edition |
| Embeddings | SentenceTransformers (local) |
| Vector retrieval | Neo4j built-in vector index |
| Operational store | PostgreSQL |
| Cache | Valkey (open-source Redis fork) |
| Tool interface | Model Context Protocol (MCP) SDK |
| LLM | Anthropic Claude API |

## Setup

1. **Start the data layer:**
   ```bash
   docker compose up -d
   ```
   Verify:
   - Neo4j browser: http://localhost:7474 (login: neo4j / testpassword123)
   - `docker compose ps` — all 4 services should show healthy/running

2. **Set up Python environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt --break-system-packages
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then fill in your gemini_model_api
   ```

4. **Run the API:**
   ```bash
   uvicorn api.main:app --reload
   ```

## Project structure

```
/ingestion      — Stage 1: event capture, validation, idempotency
/processing     — Stage 2: extraction, normalization, entity resolution
/graph          — Stage 3: Neo4j temporal graph writes, embedding sync
/retrieval      — Stage 4-5: candidate retrieval, reranking, policy filtering
/composition    — Stage 6: context package composition
/mcp_tools      — MCP tool definitions (memory.write_event, memory.query_candidates, etc.)
/api            — FastAPI app tying it all together
/report         — Design doc, architecture narrative, governance model
```

## Status

🚧 Scaffold stage — data layer defined, application code in progress.
