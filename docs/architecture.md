# Architecture

## Workflow (LangGraph)

```
                  ┌──────────┐
   user ────────▶ │ analyze  │  rewrite + classify (Groq fast model)
                  └────┬─────┘
                       ▼
                  ┌──────────┐
                  │ retrieve │  Chroma top-k similarity search
                  └────┬─────┘
                       ▼
                  ┌──────────┐
                  │  grade   │  per-chunk LLM relevance filter
                  └──┬───┬───┘
        relevant=∅   │   │   relevant>0
   (retries<MAX)     │   │
                     ▼   ▼
              ┌──────────┐  ┌──────────┐
              │ rewrite  │  │ generate │  answer + [n] citations
              └────┬─────┘  └────┬─────┘
                   │             ▼
                   │       ┌──────────┐
                   │       │grounding │  Self-RAG verifier
                   │       └────┬─────┘
                   │            ▼
                   └──▶ retrieve (loop)        END
```

## State schema (`app/rag/nodes.py:GraphState`)

| Field | Type | Set by | Used by |
|---|---|---|---|
| `question` | str | entrypoint | all |
| `rewritten_query` | str | analyze, rewrite | retrieve |
| `query_type` | str | analyze | (response only) |
| `documents` | list[LCDocument] | retrieve | grade |
| `relevant_documents` | list[LCDocument] | grade | generate, grounding |
| `retries` | int | rewrite | routing |
| `answer` | str | generate, grounding | response |
| `sources` | list[dict] | generate | response |
| `grounded` | bool | grounding | response |

## Conditional routing

After `grade`:
- `relevant_documents` non-empty → `generate`
- `relevant_documents` empty and `retries < MAX_RETRIES` → `rewrite` → `retrieve`
- `relevant_documents` empty and retries exhausted → `generate` (returns honest "I don't know")

After `generate`:
- Always → `grounding` → END
- `grounding` does not loop back: it surfaces a warning via `grounded=False` and an appended caveat in the answer. This keeps latency predictable and is a documented design choice; a stricter Self-RAG implementation could re-route here.

## Why this shape

- **Two-tier LLMs.** Generation gets the 70B Llama; grading, rewriting, and grounding use the 8B model. High-volume low-stakes classification calls don't need the big model.
- **Grader is lenient on failure.** If JSON parsing or the API call fails for a chunk, the chunk is kept rather than dropped — favors recall over a brittle false-negative.
- **Bounded retries.** The grade→rewrite loop has a hard ceiling of `MAX_RETRIES=2`. After exhaustion we still pass to `generate`, which is prompted to admit ignorance when context is empty.
- **Idempotent ingestion.** Re-ingesting a `source` deletes prior chunks (via Chroma metadata filter) before reinsertion.

## Data layout

- **Vectors:** local Chroma in `./data/chroma`, collection `tech_docs`. Metadata per chunk: `source`, `title`, `chunk_index`.
- **Relational:** PostgreSQL (`rag_assistant` DB) with three tables:
  - `documents` — registry of ingested sources
  - `query_logs` — every `/query` call, with rewrite + retries + grounded flag + sources JSON
  - `feedback` — FK to `query_logs`, thumbs up/down + comment

## Chunking strategy

- `RecursiveCharacterTextSplitter`, `chunk_size=900`, `chunk_overlap=150`.
- Separator priority: `\n## `, `\n### `, `\n\n`, `\n`, `. `, ` `, `""` — prefers structural boundaries.
- ~900 chars ≈ 200 tokens, fits MiniLM's 512-token window with headroom.
- 150-char overlap preserves cross-boundary references (e.g., "as shown above").
