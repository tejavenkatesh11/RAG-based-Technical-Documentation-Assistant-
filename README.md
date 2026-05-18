# RAG Technical Documentation Assistant

A Retrieval-Augmented Generation system for technical docs, built with a
**self-corrective LangGraph workflow** and served via **FastAPI**.

- **LLM:** Groq — Llama 3.3 70B (generation) + Llama 3.1 8B (grading / rewriting / grounding)
- **Vector store:** ChromaDB (local, persistent)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (local, free)
- **Metadata DB:** PostgreSQL (documents registry, query logs, feedback)
- **Default corpus:** 5 FastAPI tutorial pages — see [`corpus/sources.md`](corpus/sources.md)
- **Optional UI:** Streamlit

## Architecture

```
analyze ─▶ retrieve ─▶ grade ─┬─▶ generate ─▶ grounding ─▶ END
                              │      ▲
                              └─▶ rewrite ──┘   (loop, ≤ MAX_RETRIES)
```

See [`docs/architecture.md`](docs/architecture.md) for full diagram, state schema, and routing logic.

### Workflow nodes

| Node | Purpose |
|---|---|
| **analyze** | Rewrite the user query for retrieval; classify type (conceptual / how-to / troubleshooting / api-reference). |
| **retrieve** | Top-k similarity search in Chroma. |
| **grade** | Per-chunk LLM relevance check. Filters out off-topic chunks. |
| **rewrite** | (loop) Reformulate the query when no relevant chunks survive. Bounded by `MAX_RETRIES`. |
| **generate** | Final answer grounded in relevant chunks, with inline `[n]` citations. |
| **grounding** | Self-RAG style verifier — flags answers whose claims aren't supported by the context. |

## Project layout

```
app/
  main.py                 FastAPI entry + lifespan
  config.py               pydantic-settings
  logging_setup.py        structured logger
  api/                    route modules
    query.py · ingest.py · documents.py · feedback.py
  core/                   plumbing
    db.py · llm.py · vectorstore.py
  rag/                    pipeline logic
    graph.py              LangGraph wiring
    nodes.py              node functions + state schema
    prompts.py            all LLM system prompts
    ingestion.py          fetch → chunk → embed → persist
  models/
    orm.py                SQLAlchemy tables
    schemas.py            Pydantic request/response models
scripts/
  ingest_default.py       one-shot corpus ingestion
corpus/
  sources.md              default corpus + how to add yours
docs/
  architecture.md         diagram, state schema, routing
data/                     Chroma persistence (gitignored)
streamlit_app.py          minimal UI
Makefile                  install · ingest · run · ui · clean
.env · .env.example
requirements.txt
```

## Setup

Prereqs: Python 3.11+, PostgreSQL running locally, a Groq API key.

```powershell
conda activate main
pip install -r requirements.txt

# Create the database (one-time)
psql -U postgres -c "CREATE DATABASE rag_assistant;"

# Configure
copy .env.example .env
# Edit .env: set GROQ_API_KEY and DB_PASSWORD (or DATABASE_URL)
```

## Run

```powershell
# 1) Ingest the default FastAPI docs corpus
make ingest      # or: python scripts/ingest_default.py

# 2) Start the API
make run         # or: python -m uvicorn app.main:app --reload --port 8000

# 3) (Optional) Streamlit UI in another terminal
make ui          # or: streamlit run streamlit_app.py
```

Swagger UI: http://localhost:8000/docs · Streamlit UI: http://localhost:8501

## API

### `POST /query`
```json
{ "question": "How do I declare a path parameter with a type in FastAPI?" }
```
Response (truncated):
```json
{
  "query_id": 1,
  "rewritten_query": "FastAPI typed path parameter declaration syntax",
  "query_type": "api-reference",
  "answer": "To declare a path parameter with a type in FastAPI, use standard Python type annotations... [1][2]",
  "sources": [
    {"id": 1, "source": "https://fastapi.tiangolo.com/tutorial/path-params/", "title": "Path Parameters - FastAPI", "chunk_index": 1}
  ],
  "retries": 0,
  "grounded": true
}
```

### `POST /ingest`
JSON body with URLs, or multipart file upload (txt / md / html):
```json
{ "urls": ["https://fastapi.tiangolo.com/tutorial/security/"] }
```

### `GET /documents`
Lists indexed sources with chunk counts.

### `POST /feedback`
```json
{ "query_id": 1, "rating": "up", "comment": "spot on" }
```

## Design decisions & tradeoffs

**Two-tier Groq models.** Generation uses `llama-3.3-70b-versatile` for quality; grading, rewriting, and grounding use `llama-3.1-8b-instant` because they're high-volume, low-stakes classification calls. Cuts cost and latency without hurting answers.

**Self-corrective in two places.** The grade→rewrite loop handles "retrieval didn't return relevant chunks." The grounding node handles "generation hallucinated despite relevant chunks." Together they cover both retrieval failure modes and generation failure modes — the Self-RAG/CRAG patterns the assignment cites.

**Grounding flags instead of looping.** A stricter Self-RAG implementation would re-loop on grounding failure. We surface a `grounded=false` flag and append a caveat in the answer instead — keeps latency bounded and makes the failure visible to the caller, who can decide whether to retry. Documented as a tradeoff.

**Chunking: 900 chars / 150 overlap, recursive splitter.** Tech docs mix prose and code; recursive splitting prefers paragraph and heading boundaries before hard cuts. ~900 chars (~200 tokens) fits MiniLM's 512-token window with headroom. 150-char overlap preserves cross-boundary references. See [`app/rag/ingestion.py`](app/rag/ingestion.py).

**Local embeddings (MiniLM).** Groq doesn't offer embeddings and we wanted a no-extra-key path. MiniLM is small, fast, good enough for small tutorial corpora. Swap for `bge-base-en-v1.5` or OpenAI embeddings for better recall.

**Native Groq SDK with a tiny shim.** We use the `groq` SDK directly instead of `langchain-groq`, exposing only `.invoke()` and `.with_structured_output()`. Avoids version-pin conflicts in the env and keeps the LLM layer ~80 LOC ([`app/core/llm.py`](app/core/llm.py)).

**Chroma + Postgres, not pgvector.** Chroma keeps the vector layer dead simple; Postgres owns the relational surface (documents registry, query logs, feedback) where SQL is the right tool. Moving to pgvector is a one-file swap of [`app/core/vectorstore.py`](app/core/vectorstore.py).

**Grader is lenient on failure.** If the grader LLM errors on a chunk, we keep it rather than drop it — favors recall over a brittle "everything irrelevant" outcome.

**Retry cap of 2.** Hardcoded ceiling on rewrite→retrieve loops. After exhaustion the graph still routes to `generate`, which is prompted to say "I don't know" when context is empty.

**Idempotent ingestion.** Re-ingesting the same `source` deletes prior chunks in Chroma (via metadata filter) before re-adding — so re-runs don't duplicate.

**Centralized prompts.** All system prompts live in [`app/rag/prompts.py`](app/rag/prompts.py). Iterating on prompt design touches one file, not five.

## Improvements with more time

- **Web search fallback** via Tavily when retries exhaust with empty context (assignment bonus).
- **Conversation memory** via LangGraph's `MemorySaver` keyed by session id; rewrite would then condition on history (assignment bonus).
- **Hybrid retrieval** (BM25 + dense) — small corpora especially benefit.
- **Streaming** the `/query` response (LangGraph supports `astream_events`).
- **Eval harness** — a small set of (question, expected_source) pairs scored on retrieval hit-rate and answer faithfulness, plus pytest coverage of routing decisions.
- **Reranker** (cross-encoder) between retrieve and grade — would let us pull a wider top-k and let the reranker do precision.

## Assumptions

- Postgres is reachable per `.env` (the user's existing local install).
- Groq free tier is sufficient for development.
- Corpus is small (≤ a few dozen docs); no sharding/HNSW tuning needed.

## Notes on env compatibility

This project runs in the user's `conda activate main` environment. During build we found that:
- `langchain-groq` and `langchain-huggingface` couldn't coexist with the installed `langchain_core` versions, so we use the native `groq` SDK and a custom sentence-transformers wrapper instead. Functionally equivalent.
- `langchain_core`/`langchain`/`langgraph` were upgraded to versions compatible with `langgraph >= 1.x` during setup.
