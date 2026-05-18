import json

from fastapi import APIRouter, HTTPException

from app.core.db import session_scope
from app.logging_setup import get_logger
from app.models.orm import QueryLog
from app.models.schemas import QueryRequest, QueryResponse, SourceRef
from app.rag.graph import get_graph

router = APIRouter(tags=["query"])
log = get_logger("api.query")


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    graph = get_graph()
    try:
        result = graph.invoke({"question": req.question, "retries": 0})
    except Exception as e:
        log.exception("graph execution failed")
        raise HTTPException(status_code=500, detail=f"graph execution failed: {e}")

    sources = [SourceRef(**s) for s in result.get("sources", [])]
    grounded = bool(result.get("grounded", True))

    with session_scope() as s:
        log_row = QueryLog(
            question=req.question,
            rewritten_query=result.get("rewritten_query", ""),
            answer=result.get("answer", ""),
            retries=result.get("retries", 0),
            grounded=grounded,
            sources_json=json.dumps([sr.model_dump() for sr in sources]),
        )
        s.add(log_row)
        s.flush()
        query_id = log_row.id

    return QueryResponse(
        query_id=query_id,
        question=req.question,
        rewritten_query=result.get("rewritten_query", ""),
        query_type=result.get("query_type", ""),
        answer=result.get("answer", ""),
        sources=sources,
        retries=result.get("retries", 0),
        grounded=grounded,
    )
