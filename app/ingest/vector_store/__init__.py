from app.config import Settings
from app.ingest.vector_store.base import BaseVectorStore
from app.ingest.vector_store.chroma_store import ChromaVectorStore
from app.ingest.vector_store.qdrant_store import QdrantVectorStore


def create_vector_store(settings: Settings) -> BaseVectorStore:
    if settings.vector_store_mode == "chroma":
        return ChromaVectorStore(settings=settings)
    if settings.vector_store_mode == "qdrant":
        return QdrantVectorStore(settings=settings)
    raise ValueError(
        "Unsupported VECTOR_STORE_MODE. "
        f"expected='chroma|qdrant' actual='{settings.vector_store_mode}'"
    )


__all__ = ["BaseVectorStore", "ChromaVectorStore", "QdrantVectorStore", "create_vector_store"]
