from pathlib import Path
from typing import Dict, List, Tuple

from app.config import Settings
from app.ingest.models import VectorPoint
from app.ingest.vector_store.base import BaseVectorStore


class ChromaVectorStore(BaseVectorStore):
    def __init__(self, settings: Settings):
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("chromadb is not installed. Run: pip install -r requirements.txt") from exc

        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        collection_name = settings.vector_store_collection
        if settings.tenant_isolation_enabled and settings.tenant_id:
            collection_name = f"{settings.tenant_id}_{collection_name}"
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _to_record(point: VectorPoint) -> Dict[str, str]:
        # Chroma 将文本内容与元数据分离存储：text 字段存为 document（可被检索），
        # 其余字段（doc_id, source_path 等）存为 metadata（用于过滤和溯源）。
        payload = dict(point.payload)
        text = str(payload.pop("text", "")).strip()
        metadata = {str(k): str(v) for k, v in payload.items()}
        return {
            "id": point.point_id,
            "embedding": point.vector,
            "document": text,
            "metadata": metadata,
        }

    def upsert(self, points: List[VectorPoint]) -> None:
        if not points:
            return

        records = [self._to_record(point) for point in points]
        self._collection.upsert(
            ids=[record["id"] for record in records],
            embeddings=[record["embedding"] for record in records],
            documents=[record["document"] for record in records],
            metadatas=[record["metadata"] for record in records],
        )

    def delete_points(self, point_ids: List[str]) -> None:
        if not point_ids:
            return
        # Chroma 单次 delete 的 ID 数量不宜过大，分批 200 条避免请求超时或锁库。
        batch_size = 200
        for i in range(0, len(point_ids), batch_size):
            self._collection.delete(ids=point_ids[i : i + batch_size])

    def query(self, vector: List[float], top_k: int = 1) -> List[Tuple[str, float]]:
        try:
            result = self._collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                include=["distances"],
            )
            ids = (result.get("ids") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            return list(zip(ids, distances))
        except Exception:
            return []

    def query_batch(self, vectors: List[List[float]], top_k: int = 1) -> List[List[Tuple[str, float]]]:
        if not vectors:
            return []
        try:
            result = self._collection.query(
                query_embeddings=vectors,
                n_results=top_k,
                include=["distances"],
            )
            all_ids = result.get("ids") or [[] for _ in vectors]
            all_distances = result.get("distances") or [[] for _ in vectors]
            return [list(zip(ids, dists)) for ids, dists in zip(all_ids, all_distances)]
        except Exception:
            return [self.query(v, top_k=top_k) for v in vectors]
