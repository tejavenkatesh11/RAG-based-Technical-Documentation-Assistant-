"""Self-corrective RAG workflow as a LangGraph StateGraph.

    analyze -> retrieve -> grade -> (generate -> grounding -> END | rewrite -> retrieve ...)

State tracks `retries` so the grade->rewrite loop is bounded by MAX_RETRIES.
After generation, a grounding-check node verifies the answer is supported by
the retrieved context (Self-RAG style); failures are surfaced via a flag on
the response rather than another retry, to keep latency predictable.
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph

from app.config import settings
from app.rag.nodes import (
    GraphState,
    analyze_node,
    grade_node,
    generate_node,
    grounding_node,
    retrieve_node,
    rewrite_node,
)


def route_after_grade(state: GraphState) -> Literal["generate", "rewrite"]:
    if state.get("relevant_documents"):
        return "generate"
    if state.get("retries", 0) >= settings.max_retries:
        return "generate"  # give up: generate "I don't know"
    return "rewrite"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("analyze", analyze_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade", grade_node)
    g.add_node("rewrite", rewrite_node)
    g.add_node("generate", generate_node)
    g.add_node("grounding", grounding_node)

    g.set_entry_point("analyze")
    g.add_edge("analyze", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route_after_grade, {
        "generate": "generate",
        "rewrite": "rewrite",
    })
    g.add_edge("rewrite", "retrieve")
    g.add_edge("generate", "grounding")
    g.add_edge("grounding", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
