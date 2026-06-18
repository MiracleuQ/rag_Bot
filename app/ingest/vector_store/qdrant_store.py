from typing import Any, Dict, List, Optional

from app.config import Settings
from app.ingest.models import VectorPoint
from app.ingest.vector_store.base import BaseVectorStore


class QdrantVectorStore(BaseVectorStore):
    def __init__(self, settings: Settings):
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL is required when VECTOR_STORE_MODE=qdrant.")
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:
            raise ImportError("qdrant-client is not installed. Run: pip install -r requirements.txt") from exc

        client_args: Dict[str, Any] = {
            "url": settings.qdrant_url,
            "timeout": settings.qdrant_timeout_sec,
        }
        if settings.qdrant_api_key:
            client_args["api_key"] = settings.qdrant_api_key

        self._client = QdrantClient(**client_args)
        self._models = models
        self._collection = settings.vector_store_collection
        self._collection_checked = False

    def _collection_exists(self) -> bool:
        if hasattr(self._client, "collection_exists"):
            return bool(self._client.collection_exists(collection_name=self._collection))
        try:
            self._client.get_collection(collection_name=self._collection)
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_vector_size(vectors_config: Any) -> Optional[int]:
        if vectors_config is None:
            return None
        if isinstance(vectors_config, dict):
            default_vector = vectors_config.get("")
            if default_vector is not None:
                return getattr(default_vector, "size", None)
            first = next(iter(vectors_config.values()), None)
            return getattr(first, "size", None)
        return getattr(vectors_config, "size", None)

    def _ensure_collection(self, vector_size: int) -> None:
        if self._collection_checked:
            return
        if self._collection_exists():
            info = self._client.get_collection(collection_name=self._collection)
            params = getattr(getattr(info, "config", None), "params", None)
            vectors_config = getattr(params, "vectors", None)
            actual_size = self._extract_vector_size(vectors_config)
            if isinstance(actual_size, int) and actual_size != vector_size:
                raise ValueError(
                    "Qdrant collection vector size mismatch. "
                    f"collection='{self._collection}' expected={vector_size} actual={actual_size}"
                )
            self._collection_checked = True
            return

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=self._models.VectorParams(
                size=vector_size,
                distance=self._models.Distance.COSINE,
            ),
        )
        self._collection_checked = True

    @staticmethod
    def _to_payload(point: VectorPoint) -> Dict[str, str]:
        return {str(k): str(v) for k, v in dict(point.payload).items()}

    def upsert(self, points: List[VectorPoint]) -> None:
        if not points:
            return

        vector_size = len(points[0].vector)
        if vector_size <= 0:
            raise ValueError("Invalid vector size for Qdrant upsert.")
        self._ensure_collection(vector_size=vector_size)

        records = [
            self._models.PointStruct(
                id=point.point_id,
                vector=point.vector,
                payload=self._to_payload(point),
            )
            for point in points
        ]
        self._client.upsert(
            collection_name=self._collection,
            points=records,
            wait=True,
        )

    def delete_points(self, point_ids: List[str]) -> None:
        if not point_ids:
            return
        if not self._collection_exists():
            return

        batch_size = 200
        for i in range(0, len(point_ids), batch_size):
            self._client.delete(
                collection_name=self._collection,
                points_selector=self._models.PointIdsList(points=point_ids[i : i + batch_size]),
                wait=True,
            )

    def query(self, vector: List[float], top_k: int = 1) -> List[tuple]:
        if not self._collection_exists():
            return []
        try:
            if hasattr(self._client, "query_points"):
                result = self._client.query_points(
                    collection_name=self._collection,
                    query=vector,
                    limit=top_k,
                    with_payload=False,
                    with_vectors=False,
                )
                points = getattr(result, "points", None)
                if isinstance(points, list):
                    return [(str(getattr(p, "id", "")), float(getattr(p, "score", 0.0))) for p in points]
            results = self._client.search(
                collection_name=self._collection,
                query_vector=vector,
                limit=top_k,
                with_payload=False,
                with_vectors=False,
            )
            return [(str(getattr(r, "id", "")), float(getattr(r, "score", 0.0))) for r in results]
        except Exception:
            return []

    def query_batch(self, vectors: List[List[float]], top_k: int = 1) -> List[List[tuple]]:
        if not vectors:
            return []
        if not self._collection_exists():
            return [[] for _ in vectors]
        try:
            if hasattr(self._client, "query_points_batch"):
                from qdrant_client.models import QueryRequest
                requests = [
                    QueryRequest(query=v, limit=top_k, with_payload=False, with_vectors=False)
                    for v in vectors
                ]
                batch_result = self._client.query_points_batch(
                    collection_name=self._collection,
                    requests=requests,
                )
                all_results = getattr(batch_result, "responses", None)
                if isinstance(all_results, list):
                    return [
                        [(str(getattr(p, "id", "")), float(getattr(p, "score", 0.0)))
                         for p in (getattr(r, "points", None) or [])]
                        for r in all_results
                    ]
        except Exception:
            pass
        return [self.query(v, top_k=top_k) for v in vectors]
