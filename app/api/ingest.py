import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import IngestResultOut, IngestUrlRequest
from app.rag.ingestion import ingest_file, ingest_url

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=list[IngestResultOut])
async def ingest(
    payload: IngestUrlRequest | None = None,
    files: list[UploadFile] = File(default=[]),
):
    results: list[IngestResultOut] = []

    if payload and payload.urls:
        for url in payload.urls:
            try:
                r = ingest_url(str(url))
                results.append(IngestResultOut(source=r.source, title=r.title, chunks=r.chunks))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"failed to ingest {url}: {e}")

    for uf in files or []:
        suffix = Path(uf.filename or "upload").suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await uf.read())
            tmp_path = tmp.name
        try:
            r = ingest_file(tmp_path)
            results.append(IngestResultOut(source=uf.filename or r.source, title=r.title, chunks=r.chunks))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"failed to ingest {uf.filename}: {e}")

    if not results:
        raise HTTPException(status_code=400, detail="provide `urls` JSON body or `files` upload")
    return results
