from fastapi import APIRouter

from app.core.db import session_scope
from app.models.orm import Document
from app.models.schemas import DocumentOut

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=list[DocumentOut])
def list_documents():
    with session_scope() as s:
        rows = s.query(Document).order_by(Document.created_at.desc()).all()
        return [
            DocumentOut(
                id=d.id,
                source=d.source,
                title=d.title,
                source_type=d.source_type,
                chunk_count=d.chunk_count,
            )
            for d in rows
        ]
