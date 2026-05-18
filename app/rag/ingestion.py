"""Document ingestion: fetch -> clean -> chunk -> embed -> persist.

Chunking strategy: RecursiveCharacterTextSplitter, size=900, overlap=150.
- Technical docs mix prose, code blocks, and headings. Recursive splitting prefers
  paragraph/section boundaries before hard cuts, preserving code-with-context.
- ~900 chars (~200 tokens) fits comfortably in MiniLM's 512-token window and
  leaves room for multi-chunk context in the LLM prompt.
- 150-char overlap keeps cross-boundary references (e.g., "as shown above")
  retrievable from either side.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from markdownify import markdownify

from app.core.db import session_scope
from app.core.vectorstore import get_vectorstore
from app.logging_setup import get_logger
from app.models.orm import Document

log = get_logger("rag.ingest")


@dataclass
class IngestResult:
    source: str
    title: str
    chunks: int


def _fetch_url(url: str) -> tuple[str, str]:
    r = httpx.get(url, follow_redirects=True, timeout=30.0, headers={"User-Agent": "rag-assistant/1.0"})
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)
    main = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in main.select("nav, footer, script, style, .toc, .sidebar"):
        tag.decompose()
    md = markdownify(str(main), heading_style="ATX")
    return title, md


def _read_file(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        soup = BeautifulSoup(text, "lxml")
        text = markdownify(str(soup), heading_style="ATX")
    return path.stem, text


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )


def _chunk_id(source: str, idx: int, text: str) -> str:
    h = hashlib.sha1(f"{source}|{idx}|{text[:64]}".encode()).hexdigest()[:16]
    return f"{h}-{idx}"


def _ingest_text(source: str, title: str, text: str, source_type: str) -> IngestResult:
    splitter = _splitter()
    chunks = splitter.split_text(text)
    docs: list[LCDocument] = []
    ids: list[str] = []
    for i, chunk in enumerate(chunks):
        docs.append(LCDocument(
            page_content=chunk,
            metadata={"source": source, "title": title, "chunk_index": i},
        ))
        ids.append(_chunk_id(source, i, chunk))

    vs = get_vectorstore()
    try:
        vs.delete(where={"source": source})
    except Exception:
        pass
    vs.add_documents(docs, ids=ids)

    with session_scope() as s:
        existing = s.query(Document).filter(Document.source == source).one_or_none()
        if existing:
            existing.title = title
            existing.chunk_count = len(chunks)
            existing.source_type = source_type
        else:
            s.add(Document(source=source, title=title, chunk_count=len(chunks), source_type=source_type))

    log.info("ingested source=%s title=%r chunks=%d", source, title[:60], len(chunks))
    return IngestResult(source=source, title=title, chunks=len(chunks))


def ingest_url(url: str) -> IngestResult:
    title, md = _fetch_url(url)
    return _ingest_text(url, title, md, source_type="url")


def ingest_file(path: str | Path) -> IngestResult:
    p = Path(path)
    title, text = _read_file(p)
    return _ingest_text(str(p.resolve()), title, text, source_type="file")


def ingest_urls(urls: Iterable[str]) -> list[IngestResult]:
    return [ingest_url(u) for u in urls]


DEFAULT_CORPUS = [
    "https://fastapi.tiangolo.com/tutorial/first-steps/",
    "https://fastapi.tiangolo.com/tutorial/path-params/",
    "https://fastapi.tiangolo.com/tutorial/query-params/",
    "https://fastapi.tiangolo.com/tutorial/body/",
    "https://fastapi.tiangolo.com/tutorial/dependencies/",
]
