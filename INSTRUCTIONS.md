# Instructions

Step-by-step guide to set up, run, and operate the RAG Technical Docs Assistant.
For architecture and design rationale, see [README.md](README.md) and [docs/architecture.md](docs/architecture.md).

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | The project is verified on the user's `conda activate main` env (Python 3.13). |
| PostgreSQL | 13+ | Running locally on port 5432. |
| Groq API key | — | Get one at https://console.groq.com/keys (free tier is sufficient). |
| OS | Windows / macOS / Linux | All commands below are PowerShell; bash equivalents are obvious. |

---

## 2. First-time setup

### 2.1 Activate the environment

```powershell
conda activate main
```

### 2.2 Install dependencies

```powershell
pip install -r requirements.txt
```

Notes:
- All packages are soft-pinned in [requirements.txt](requirements.txt).
- We use the native `groq` SDK and a custom sentence-transformers wrapper instead of `langchain-groq` / `langchain-huggingface` — intentional, see [README.md](README.md#notes-on-env-compatibility).

### 2.3 Create the PostgreSQL database

```powershell
psql -U postgres -c "CREATE DATABASE rag_assistant;"
```

Tables (`documents`, `query_logs`, `feedback`) are created automatically by [app/core/db.py](app/core/db.py) on first server start.

### 2.4 Configure environment variables

```powershell
copy .env.example .env
```

Then edit [.env](.env) and set at minimum:

```env
GROQ_API_KEY=gsk_...
DB_PASSWORD=<your postgres password>
```

All other settings have working defaults — see [.env.example](.env.example) for the full list.

---

## 3. Ingest the default corpus

The default corpus is **5 pages of the FastAPI tutorial** (see [corpus/sources.md](corpus/sources.md)).

```powershell
python scripts/ingest_default.py
```

Expected output:
```
OK   26 chunks  First Steps - FastAPI         <- https://fastapi.tiangolo.com/...
OK   20 chunks  Path Parameters - FastAPI     <- https://fastapi.tiangolo.com/...
OK   10 chunks  Query Parameters - FastAPI    <- https://fastapi.tiangolo.com/...
OK   15 chunks  Request Body - FastAPI        <- https://fastapi.tiangolo.com/...
OK   22 chunks  Dependencies - FastAPI        <- https://fastapi.tiangolo.com/...
```

Ingestion is idempotent — re-running deletes the prior chunks for each `source` before re-adding, so duplicate runs are safe.

---

## 4. Run the application

### 4.1 Start the FastAPI server

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Or via the Makefile:
```powershell
make run
```

Endpoints available at:
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- Health check: http://localhost:8000/health

### 4.2 (Optional) Start the Streamlit UI

In a **second terminal**, with the API still running:

```powershell
streamlit run streamlit_app.py
```

Or:
```powershell
make ui
```

The UI is at http://localhost:8501. It calls the FastAPI server on port 8000.

---

## 5. Using the API

### 5.1 Ask a question — `POST /query`

```powershell
curl -X POST http://localhost:8000/query `
  -H "Content-Type: application/json" `
  -d '{\"question\": \"How do I declare a path parameter with a type in FastAPI?\"}'
```

Response shape:
```json
{
  "query_id": 1,
  "question": "...",
  "rewritten_query": "FastAPI typed path parameter declaration syntax",
  "query_type": "api-reference",
  "answer": "To declare a path parameter with a type... [1][3]",
  "sources": [
    { "id": 1, "source": "https://...", "title": "...", "chunk_index": 1 }
  ],
  "retries": 0,
  "grounded": true
}
```

Field guide:
- `rewritten_query` — what the analyze node sent to retrieval (useful for debugging recall).
- `query_type` — one of `conceptual` / `how-to` / `troubleshooting` / `api-reference` / `other`.
- `retries` — how many times the grade→rewrite loop fired (cap = `MAX_RETRIES`, default 2).
- `grounded` — `false` means the grounding node flagged unsupported claims; a caveat is appended to `answer`.

### 5.2 Ingest more docs — `POST /ingest`

URLs:
```powershell
curl -X POST http://localhost:8000/ingest `
  -H "Content-Type: application/json" `
  -d '{\"urls\": [\"https://fastapi.tiangolo.com/tutorial/security/\"]}'
```

File upload (multipart):
```powershell
curl -X POST http://localhost:8000/ingest `
  -F "files=@./my_doc.md"
```

Supported file types: `.md`, `.txt`, `.html`, `.htm`.

### 5.3 List indexed docs — `GET /documents`

```powershell
curl http://localhost:8000/documents
```

### 5.4 Submit feedback — `POST /feedback`

```powershell
curl -X POST http://localhost:8000/feedback `
  -H "Content-Type: application/json" `
  -d '{\"query_id\": 1, \"rating\": \"up\", \"comment\": \"useful\"}'
```

`rating` must be `"up"` or `"down"`.

---

## 6. Operations

### 6.1 Reset the vector store

```powershell
Remove-Item -Recurse -Force data/chroma
python scripts/ingest_default.py
```

This wipes the Chroma persistence and re-ingests from scratch. Postgres rows in `documents` will be overwritten on re-ingestion.

### 6.2 Reset the database

```powershell
psql -U postgres -c "DROP DATABASE rag_assistant;"
psql -U postgres -c "CREATE DATABASE rag_assistant;"
# Tables recreate on next server start
python scripts/ingest_default.py
```

### 6.3 Change Groq models

Edit [.env](.env):
```env
GROQ_MODEL=llama-3.3-70b-versatile      # used by generation
GROQ_MODEL_FAST=llama-3.1-8b-instant    # used by analyze / grade / rewrite / grounding
```

Available models: https://console.groq.com/docs/models

### 6.4 Tune retrieval

In [.env](.env):
```env
TOP_K=4          # chunks retrieved per query
MAX_RETRIES=2    # cap on grade→rewrite loops
```

### 6.5 Swap the embedding model

In [.env](.env):
```env
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2     # default, fast
# EMBEDDING_MODEL=BAAI/bge-base-en-v1.5                    # higher quality, slower
```

After changing, you **must** wipe and re-ingest (different model = different embedding space):
```powershell
Remove-Item -Recurse -Force data/chroma
python scripts/ingest_default.py
```

---

## 7. Troubleshooting

### 7.1 `password authentication failed for user "postgres"`

The credentials in [.env](.env) don't match your local Postgres install. Either:
- Update `DB_PASSWORD` (or `DATABASE_URL`) in [.env](.env), **or**
- Reset the postgres user's password:
  ```powershell
  psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'your_new_password';"
  ```

### 7.2 `column "grounded" of relation "query_logs" does not exist`

You're running against a database created before the v0.2 grounding node was added. Run:
```powershell
psql -U postgres -d rag_assistant -c "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS grounded BOOLEAN NOT NULL DEFAULT TRUE;"
```

### 7.3 `GROQ_API_KEY` is empty or invalid

Symptom: graph execution returns 500 with an authentication error.
Fix: set `GROQ_API_KEY` in [.env](.env) and restart the server (uvicorn's `--reload` should auto-pick it up).

### 7.4 Streamlit can't reach the API

The UI hardcodes `API_BASE = "http://localhost:8000"` in [streamlit_app.py](streamlit_app.py). Confirm the FastAPI server is running on port 8000 (`curl http://localhost:8000/health`).

### 7.5 Slow first query

First call after server start loads the sentence-transformers model into memory (~100 MB). Subsequent calls are fast. The `lifespan` hook in [app/main.py](app/main.py) only compiles the graph eagerly — it doesn't pre-load embeddings.

**On this machine**, the default embedding model (`sentence-transformers/all-MiniLM-L6-v2`) is **already cached** at:

```
C:\Users\shash\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2
```

So first-time startup does **not** require a download — it loads from local disk into RAM. Also cached and available as a drop-in upgrade: `sentence-transformers/all-mpnet-base-v2` (higher quality, ~3x larger).

If you switch `EMBEDDING_MODEL` in [.env](.env) to a model that isn't cached yet, the first ingestion will download it (one-time, then cached for future runs).

### 7.6 `pip` installs to the wrong interpreter

If you see "Package X is not installed" warnings in the IDE despite a successful install, your IDE's selected Python interpreter probably differs from the conda `main` env. Use `python -m pip install ...` (not bare `pip`) to bind to the active interpreter, and point your IDE at `C:\Users\<you>\miniconda3\python.exe`.

---

## 8. Quick reference — Makefile targets

| Target | Command | Purpose |
|---|---|---|
| `make install` | `python -m pip install -r requirements.txt` | Install dependencies |
| `make ingest` | `python scripts/ingest_default.py` | Ingest the default FastAPI corpus |
| `make run` | `python -m uvicorn app.main:app --reload --port 8000` | Start the API server |
| `make ui` | `streamlit run streamlit_app.py` | Start the Streamlit UI |
| `make clean` | `rm -rf data/chroma __pycache__` | Wipe Chroma + Python caches |

---

## 9. Project layout (quick map)

| Path | Contents |
|---|---|
| [app/main.py](app/main.py) | FastAPI entry, lifespan, CORS, router registration |
| [app/config.py](app/config.py) | pydantic-settings — reads [.env](.env) |
| [app/api/](app/api/) | Route modules, one per resource |
| [app/core/](app/core/) | DB engine, LLM client, vector store |
| [app/rag/graph.py](app/rag/graph.py) | LangGraph wiring |
| [app/rag/nodes.py](app/rag/nodes.py) | Node functions + `GraphState` schema |
| [app/rag/prompts.py](app/rag/prompts.py) | All system prompts |
| [app/rag/ingestion.py](app/rag/ingestion.py) | URL/file → chunk → embed → persist |
| [app/models/orm.py](app/models/orm.py) | SQLAlchemy tables |
| [app/models/schemas.py](app/models/schemas.py) | Pydantic request/response models |
| [scripts/ingest_default.py](scripts/ingest_default.py) | One-shot corpus loader |
| [corpus/sources.md](corpus/sources.md) | Default corpus reference |
| [docs/architecture.md](docs/architecture.md) | Diagrams, state schema, routing |
| [streamlit_app.py](streamlit_app.py) | Optional UI |
| [data/chroma/](data/) | Chroma persistence (gitignored) |
