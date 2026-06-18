from typing import Any, Dict, List

from app.config import Settings
from app.ingest.embedders import BaseEmbedder
from app.retrievers.base import BaseRetriever
from app.schemas import Document


class QdrantRetriever(BaseRetriever):
    def __init__(self, settings: Settings, embedder: BaseEmbedder):
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL is required when RETRIEVER_MODE=qdrant.")
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise ImportError("qdrant-client is not installed. Run: pip install -r requirements.txt") from exc

        client_args: Dict[str, Any] = {
            "url": settings.qdrant_url,
            "timeout": settings.qdrant_timeout_sec,
        }
        if settings.qdrant_api_key:
            client_args["api_key"] = settings.qdrant_api_key

        self._settings = settings
        self._embedder = embedder
        self._client = QdrantClient(**client_args)
        self._collection = settings.vector_store_collection

    def _collection_exists(self) -> bool:
        if hasattr(self._client, "collection_exists"):
            return bool(self._client.collection_exists(collection_name=self._collection))
        try:
            self._client.get_collection(collection_name=self._collection)
            return True
        except Exception:
            return False

    def _query_points(self, query_vector: List[float], limit: int) -> List[Any]:
        if hasattr(self._client, "query_points"):
            result = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            points = getattr(result, "points", None)
            if isinstance(points, list):
                return points
        return self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

    def _build_documents(
        self,
        points: List[Any],
        limit: int,
        apply_distance_filter: bool,
    ) -> List[Document]:
        docs: List[Document] = []
        seen_keys = set()
        max_distance = self._settings.rag_max_retrieval_distance
        min_chunk_chars = max(1, self._settings.rag_min_chunk_chars)

        for idx, point in enumerate(points, start=1):
            payload = dict(getattr(point, "payload", {}) or {})
            content = str(payload.get("text", "")).strip()
            if len(content) < min_chunk_chars:
                continue

            score = getattr(point, "score", None)
            score_value = float(score) if isinstance(score, (int, float)) else None
            distance = (1.0 - score_value) if score_value is not None else None
            if (
                apply_distance_filter
                and isinstance(distance, (int, float))
                and max_distance > 0
                and float(distance) > max_distance
            ):
                continue

            doc_id = str(payload.get("doc_id") or f"doc-{idx}")
            source = str(payload.get("source_path") or payload.get("relative_path") or "")
            dedupe_key = (doc_id, content)
            if dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            docs.append(Document(doc_id=doc_id, content=content, source=source, score=score_value))
            if len(docs) >= limit:
                break
        return docs

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        question = query.strip()
        if not question:
            return []
        if not self._collection_exists():
            return []

        limit = max(1, top_k)
        candidate_k = max(limit, self._settings.rag_candidate_k)
        query_vector = self._embedder.embed_texts([question])[0]
        points = self._query_points(query_vector=query_vector, limit=candidate_k)

        filtered_docs = self._build_documents(
            points=points,
            limit=limit,
            apply_distance_filter=True,
        )
        if filtered_docs:
            return filtered_docs

        return self._build_documents(
            points=points,
            limit=limit,
            apply_distance_filter=False,
        )

    def get_docs_by_ids(self, ids: List[str]) -> List[Document]:
        if not ids:
            return []
        try:
            points = self._client.retrieve(
                collection_name=self._collection,
                ids=ids,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            return []
        docs: List[Document] = []
        for point in points:
            payload = dict(getattr(point, "payload", {}) or {})
            content = str(payload.get("text", "")).strip()
            doc_id = str(payload.get("doc_id", ""))
            source = str(payload.get("source_path", ""))
            docs.append(Document(doc_id=doc_id, content=content, source=source, score=None))
        return docs
