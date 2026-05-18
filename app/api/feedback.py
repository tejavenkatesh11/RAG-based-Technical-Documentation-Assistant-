from fastapi import APIRouter, HTTPException

from app.core.db import session_scope
from app.models.orm import Feedback, QueryLog
from app.models.schemas import FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    with session_scope() as s:
        q = s.query(QueryLog).filter(QueryLog.id == req.query_id).one_or_none()
        if not q:
            raise HTTPException(status_code=404, detail="query_id not found")
        s.add(Feedback(query_id=req.query_id, rating=req.rating, comment=req.comment))
    return {"ok": True}
