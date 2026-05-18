from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from app.config import settings


class SentenceTransformerEmbeddings(Embeddings):
    """LangChain Embeddings wrapper over sentence-transformers.

    Avoids depending on `langchain-huggingface` (newer langchain_core required).
    """

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vecs.tolist()

    def embed_query(self, text: str) -> list[float]:
        vec = self._model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0]
        return vec.tolist()


@lru_cache(maxsize=1)
def get_embeddings() -> SentenceTransformerEmbeddings:
    return SentenceTransformerEmbeddings(settings.embedding_model)


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def get_retriever(k: int | None = None):
    return get_vectorstore().as_retriever(search_kwargs={"k": k or settings.top_k})
