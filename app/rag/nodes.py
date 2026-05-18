"""LangGraph node functions, kept separate from graph wiring for testability."""
from __future__ import annotations

from typing import Literal, TypedDict

from langchain_core.documents import Document as LCDocument
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.llm import get_fast_llm, get_llm
from app.core.vectorstore import get_retriever
from app.logging_setup import get_logger
from app.rag import prompts

log = get_logger("rag.nodes")


class GraphState(TypedDict, total=False):
    question: str
    rewritten_query: str
    query_type: str
    documents: list[LCDocument]
    relevant_documents: list[LCDocument]
    retries: int
    grounded: bool
    answer: str
    sources: list[dict]


# ---------- Structured-output schemas ----------

class QueryAnalysis(BaseModel):
    rewritten_query: str = Field(description="An improved, retrieval-friendly version of the question.")
    query_type: Literal["conceptual", "how-to", "troubleshooting", "api-reference", "other"] = "other"


class GradeDecision(BaseModel):
    relevant: bool = Field(description="True if the chunk helps answer the question.")


class GroundingDecision(BaseModel):
    grounded: bool = Field(description="True if every factual claim in the answer is supported by the context.")


# ---------- Nodes ----------

def analyze_node(state: GraphState) -> GraphState:
    llm = get_fast_llm().with_structured_output(QueryAnalysis)
    res: QueryAnalysis = llm.invoke([
        SystemMessage(content=prompts.QUERY_ANALYSIS),
        HumanMessage(content=state["question"]),
    ])
    log.info("analyze: type=%s rewritten=%r", res.query_type, res.rewritten_query)
    return {
        "rewritten_query": res.rewritten_query,
        "query_type": res.query_type,
        "retries": state.get("retries", 0),
    }


def retrieve_node(state: GraphState) -> GraphState:
    query = state.get("rewritten_query") or state["question"]
    docs = get_retriever().invoke(query)
    log.info("retrieve: query=%r got=%d chunks", query, len(docs))
    return {"documents": docs}


def grade_node(state: GraphState) -> GraphState:
    llm = get_fast_llm().with_structured_output(GradeDecision)
    question = state["question"]
    relevant: list[LCDocument] = []
    for doc in state.get("documents", []):
        try:
            decision: GradeDecision = llm.invoke([
                SystemMessage(content=prompts.DOC_GRADER),
                HumanMessage(content=f"Question: {question}\n\n---\nChunk:\n{doc.page_content}"),
            ])
            if decision.relevant:
                relevant.append(doc)
        except Exception as e:
            # Be lenient: keep the doc on grader failure to favor recall.
            log.warning("grader error, keeping doc: %s", e)
            relevant.append(doc)
    log.info("grade: kept %d/%d", len(relevant), len(state.get("documents", [])))
    return {"relevant_documents": relevant}


def rewrite_node(state: GraphState) -> GraphState:
    llm = get_fast_llm()
    prior = state.get("rewritten_query") or state["question"]
    msg = llm.invoke([
        SystemMessage(content=prompts.QUERY_REWRITE),
        HumanMessage(content=f"Original question: {state['question']}\nPrevious query: {prior}"),
    ])
    new_q = msg.content.strip().strip('"')
    retries = state.get("retries", 0) + 1
    log.info("rewrite: retry=%d new_query=%r", retries, new_q)
    return {"rewritten_query": new_q, "retries": retries}


def generate_node(state: GraphState) -> GraphState:
    docs = state.get("relevant_documents") or []
    if not docs:
        log.info("generate: no relevant docs, emitting fallback answer")
        return {
            "answer": (
                "I don't have enough information in the indexed documents to answer that. "
                "Try rephrasing or ingesting more relevant docs."
            ),
            "sources": [],
            "grounded": True,
        }

    context_blocks = []
    sources = []
    for i, d in enumerate(docs, start=1):
        context_blocks.append(f"[{i}] ({d.metadata.get('title','')})\n{d.page_content}")
        sources.append({
            "id": i,
            "source": d.metadata.get("source", "unknown"),
            "title": d.metadata.get("title", ""),
            "chunk_index": d.metadata.get("chunk_index"),
        })
    context = "\n\n".join(context_blocks)

    llm = get_llm()
    msg = llm.invoke([
        SystemMessage(content=prompts.GENERATION),
        HumanMessage(content=f"Question: {state['question']}\n\nContext:\n{context}"),
    ])
    answer = msg.content.strip()
    log.info("generate: answer_len=%d sources=%d", len(answer), len(sources))
    return {"answer": answer, "sources": sources}


def grounding_node(state: GraphState) -> GraphState:
    """Self-RAG style hallucination check.

    Verifies that every claim in the generated answer is supported by the retrieved
    context. On failure, the answer is appended with a caveat and `grounded=False`
    is set; the routing function can choose to retry or just surface the warning.
    """
    docs = state.get("relevant_documents") or []
    answer = state.get("answer", "")
    if not docs or not answer:
        return {"grounded": True}

    context = "\n\n".join(f"[{i+1}] {d.page_content}" for i, d in enumerate(docs))
    llm = get_fast_llm().with_structured_output(GroundingDecision)
    try:
        decision: GroundingDecision = llm.invoke([
            SystemMessage(content=prompts.GROUNDING_CHECK),
            HumanMessage(content=f"Context:\n{context}\n\n---\nAnswer:\n{answer}"),
        ])
        grounded = decision.grounded
    except Exception as e:
        log.warning("grounding check error, assuming grounded: %s", e)
        grounded = True

    log.info("grounding: grounded=%s", grounded)
    if not grounded:
        answer = (
            answer.rstrip()
            + "\n\n_Note: the verifier flagged this answer as possibly not fully grounded in the indexed docs._"
        )
    return {"grounded": grounded, "answer": answer}
