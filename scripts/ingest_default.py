"""Standalone script: ingest the default FastAPI docs corpus into Chroma + Postgres."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import init_db
from app.logging_setup import setup_logging
from app.rag.ingestion import DEFAULT_CORPUS, ingest_url


def main() -> None:
    setup_logging()
    init_db()
    for url in DEFAULT_CORPUS:
        try:
            res = ingest_url(url)
            print(f"OK  {res.chunks:>3} chunks  {res.title[:60]}  <- {url}")
        except Exception as e:
            print(f"ERR {url}: {e}")


if __name__ == "__main__":
    main()
