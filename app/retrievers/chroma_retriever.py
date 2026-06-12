import re
from pathlib import Path
from typing import List

from app.config import Settings
from app.ingest.embedders import BaseEmbedder
from app.retrievers.base import BaseRetriever
from app.schemas import Document

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class ChromaRetriever(BaseRetriever):
    def __init__(self, settings: Settings, embedder: BaseEmbedder):
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("chromadb is not installed. Run: pip install -r requirements.txt") from exc

        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=settings.vector_store_collection,
            # cosine 距离与 OpenAI embedding 的归一化向量匹配，1 - distance 即为余弦相似度。
            metadata={"hnsw:space": "cosine"},
        )
        self._settings = settings
        self._embedder = embedder

    @staticmethod
    def _tokenize_for_overlap(text: str) -> set[str]:
        normalized = str(text or "").lower().strip()
        if not normalized:
            return set()
        tokens = set(_TOKEN_RE.findall(normalized))
        chinese_chars = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
        if len(chinese_chars) == 1:
            tokens.add(chinese_chars[0])
        for idx in range(0, max(len(chinese_chars) - 1, 0)):
            tokens.add("".join(chinese_chars[idx : idx + 2]))
        return {token for token in tokens if token}

    @classmethod
    def _source_overlap_score(cls, query: str, source: str) -> float:
        query_tokens = cls._tokenize_for_overlap(query)
        if not query_tokens:
            return 0.0
        source_tokens = cls._tokenize_for_overlap(Path(source).name)
        if not source_tokens:
            return 0.0
        hit_count = len(query_tokens.intersection(source_tokens))
        return hit_count / max(1, len(query_tokens))

    def _build_documents(
        self,
        query: str,
        raw_docs: List[str],
        raw_metadatas: List[dict],
        raw_distances: List[float],
        limit: int,
        apply_distance_filter: bool,
    ) -> List[Document]:
        candidates: List[dict] = []
        max_distance = self._settings.rag_max_retrieval_distance
        min_chunk_chars = max(1, self._settings.rag_min_chunk_chars)

        for idx, text in enumerate(raw_docs, start=1):
            content = str(text or "").strip()
            if len(content) < min_chunk_chars:
                continue

            metadata = raw_metadatas[idx - 1] if idx - 1 < len(raw_metadatas) else {}
            distance = raw_distances[idx - 1] if idx - 1 < len(raw_distances) else None
            score = None
            if isinstance(distance, (int, float)):
                # cosine distance ∈ [0, 2]，转为相似度 score ∈ [1, -1]，越接近 1 越相关。
                score = 1.0 - float(distance)
            if (
                apply_distance_filter
                and isinstance(distance, (int, float))
                and max_distance > 0
                and float(distance) > max_distance
            ):
                continue

            meta = metadata or {}
            doc_id = str(meta.get("doc_id") or f"doc-{idx}")
            source = str(meta.get("source_path") or meta.get("relative_path") or "")
            source_overlap = self._source_overlap_score(query=query, source=source)
            base_score = float(score) if isinstance(score, (int, float)) else -1.0
            final_rank = base_score + 0.20 * source_overlap
            candidates.append(
                {
                    "doc_id": doc_id,
                    "content": content,
                    "source": source,
                    "score": score,
                    "rank": final_rank,
                    "source_overlap": source_overlap,
                }
            )

        candidates.sort(
            key=lambda item: (
                float(item["rank"]),
                float(item["score"]) if isinstance(item["score"], (int, float)) else float("-inf"),
                float(item["source_overlap"]),
            ),
            reverse=True,
        )

        docs: List[Document] = []
        seen_keys = set()
        for item in candidates:
            dedupe_key = (str(item["doc_id"]), str(item["content"]))
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            docs.append(
                Document(
                    doc_id=str(item["doc_id"]),
                    content=str(item["content"]),
                    source=str(item["source"]),
                    score=float(item["score"]) if isinstance(item["score"], (int, float)) else None,
                )
            )
            if len(docs) >= limit:
                break
        return docs

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        question = query.strip()
        if not question:
            return []

        limit = max(1, top_k)
        # 从 Chroma 多取一些候选（candidate_k ≥ limit），
        # 给后续的距离筛选和去重留足余量，避免最终结果不足 top_k。
        candidate_k = max(limit, self._settings.rag_candidate_k)
        query_vector = self._embedder.embed_texts([question])[0]
        result = self._collection.query(
            query_embeddings=[query_vector],
            n_results=candidate_k,
            include=["documents", "metadatas", "distances"],
        )

        raw_docs = (result.get("documents") or [[]])[0]
        raw_metadatas = (result.get("metadatas") or [[]])[0]
        raw_distances = (result.get("distances") or [[]])[0]

        filtered_docs = self._build_documents(
            query=question,
            raw_docs=raw_docs,
            raw_metadatas=raw_metadatas,
            raw_distances=raw_distances,
            limit=limit,
            apply_distance_filter=True,
        )
        if filtered_docs:
            return filtered_docs

        # 距离筛选可能因阈值过严导致零结果（如知识库内容与查询语义差距大时）。
        # 此时放弃距离筛选，返回原始候选，确保至少有一些参考文档。
        return self._build_documents(
            query=question,
            raw_docs=raw_docs,
            raw_metadatas=raw_metadatas,
            raw_distances=raw_distances,
            limit=limit,
            apply_distance_filter=False,
        )
