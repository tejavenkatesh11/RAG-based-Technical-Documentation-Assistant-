# Default Corpus

The default corpus indexed by `scripts/ingest_default.py` is 5 pages of the
official **FastAPI tutorial**, chosen because they are concise, code-heavy,
and represent the kinds of technical Q&A the system is designed for.

| # | URL | Why |
|---|---|---|
| 1 | https://fastapi.tiangolo.com/tutorial/first-steps/ | Foundational concepts; baseline for "what is X" queries. |
| 2 | https://fastapi.tiangolo.com/tutorial/path-params/ | Common api-reference / how-to questions. |
| 3 | https://fastapi.tiangolo.com/tutorial/query-params/ | Distinguishes from path params — good for disambiguation. |
| 4 | https://fastapi.tiangolo.com/tutorial/body/ | Pydantic body models — multi-section content tests chunking. |
| 5 | https://fastapi.tiangolo.com/tutorial/dependencies/ | Conceptual + how-to — exercises query-type classification. |

## Re-running ingestion

Ingestion is idempotent: re-ingesting an existing `source` URL deletes the prior
chunks in Chroma (matched by metadata) before inserting the new ones, so the
script is safe to run multiple times.

## Using your own corpus

- **Via the API:** `POST /ingest` with `{"urls": ["https://..."]}` or multipart file upload.
- **Via the script:** edit `DEFAULT_CORPUS` in [`app/rag/ingestion.py`](../app/rag/ingestion.py).
