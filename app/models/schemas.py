from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SourceRef(BaseModel):
    id: int
    source: str
    title: str = ""
    chunk_index: Optional[int] = None


class QueryResponse(BaseModel):
    query_id: int
    question: str
    rewritten_query: str = ""
    query_type: str = ""
    answer: str
    sources: list[SourceRef] = []
    retries: int = 0
    grounded: bool = True


class IngestUrlRequest(BaseModel):
    urls: list[HttpUrl]


class IngestResultOut(BaseModel):
    source: str
    title: str
    chunks: int


class DocumentOut(BaseModel):
    id: int
    source: str
    title: str
    source_type: str
    chunk_count: int


class FeedbackRequest(BaseModel):
    query_id: int
    rating: Literal["up", "down"]
    comment: str = ""
