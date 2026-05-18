"""Minimal Streamlit UI for the RAG assistant.

Run with: `streamlit run streamlit_app.py` (after the FastAPI server is up on :8000).
"""
from __future__ import annotations

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"


def _api_get(path: str):
    with httpx.Client(timeout=30.0) as c:
        return c.get(f"{API_BASE}{path}")


def _api_post(path: str, json=None):
    with httpx.Client(timeout=180.0) as c:
        return c.post(f"{API_BASE}{path}", json=json)


st.set_page_config(page_title="RAG Docs Assistant", page_icon="📚", layout="wide")
st.title("📚 RAG Technical Docs Assistant")
st.caption("Self-corrective LangGraph workflow over your indexed technical documentation.")

with st.sidebar:
    st.subheader("Indexed documents")
    try:
        r = _api_get("/documents")
        if r.status_code == 200:
            docs = r.json()
            if not docs:
                st.info("No documents yet. Use the ingest section below.")
            for d in docs:
                st.write(f"**{d['title'][:50]}**  \n_{d['chunk_count']} chunks · {d['source_type']}_")
        else:
            st.error(f"GET /documents failed: {r.status_code}")
    except Exception as e:
        st.error(f"API unreachable: {e}")

    st.divider()
    st.subheader("Ingest a URL")
    new_url = st.text_input("URL", placeholder="https://...")
    if st.button("Ingest", use_container_width=True) and new_url:
        with st.spinner("Fetching, chunking, embedding..."):
            r = _api_post("/ingest", json={"urls": [new_url]})
        if r.status_code == 200:
            st.success(f"Ingested: {r.json()[0]['title']} ({r.json()[0]['chunks']} chunks)")
            st.rerun()
        else:
            st.error(r.text)


if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: question, response

question = st.text_input("Ask a question about the indexed docs", placeholder="How do I declare a path parameter with a type in FastAPI?")

col1, col2 = st.columns([1, 1])
with col1:
    submit = st.button("Ask", type="primary", use_container_width=True)
with col2:
    if st.button("Clear history", use_container_width=True):
        st.session_state.history = []

if submit and question.strip():
    with st.spinner("Running graph: analyze → retrieve → grade → generate → grounding…"):
        try:
            r = _api_post("/query", json={"question": question.strip()})
        except Exception as e:
            st.error(f"API error: {e}")
            r = None
    if r is not None:
        if r.status_code == 200:
            data = r.json()
            st.session_state.history.insert(0, {"q": question.strip(), "r": data})
        else:
            st.error(r.text)

for i, item in enumerate(st.session_state.history):
    data = item["r"]
    with st.container(border=True):
        st.markdown(f"**Q:** {item['q']}")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Type", data.get("query_type", "—"))
        col_b.metric("Retries", data.get("retries", 0))
        col_c.metric("Grounded", "✅" if data.get("grounded", True) else "⚠️")
        col_d.metric("Sources", len(data.get("sources", [])))

        st.markdown(f"**Rewritten query:** _{data.get('rewritten_query', '')}_")
        st.markdown("**Answer**")
        st.write(data["answer"])

        if data.get("sources"):
            with st.expander("Sources"):
                for s in data["sources"]:
                    st.markdown(f"- **[{s['id']}]** [{s['title']}]({s['source']})  (chunk {s.get('chunk_index')})")

        # Feedback
        fb_col1, fb_col2, _ = st.columns([1, 1, 4])
        if fb_col1.button("👍", key=f"up-{i}-{data['query_id']}"):
            _api_post("/feedback", json={"query_id": data["query_id"], "rating": "up"})
            st.toast("Thanks!")
        if fb_col2.button("👎", key=f"down-{i}-{data['query_id']}"):
            _api_post("/feedback", json={"query_id": data["query_id"], "rating": "down"})
            st.toast("Recorded.")
