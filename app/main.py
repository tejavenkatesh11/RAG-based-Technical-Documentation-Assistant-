from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, feedback, ingest, query
from app.core.db import init_db
from app.logging_setup import setup_logging, get_logger
from app.rag.graph import get_graph

log = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    get_graph()  # warm compile
    log.info("startup complete")
    yield
    log.info("shutdown")


app = FastAPI(
    title="RAG Technical Docs Assistant",
    description="Self-corrective RAG over technical documentation using LangGraph + Groq.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(query.router)
app.include_router(ingest.router)
app.include_router(documents.router)
app.include_router(feedback.router)
