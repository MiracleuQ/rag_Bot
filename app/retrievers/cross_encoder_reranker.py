import logging
from typing import List

from app.retrievers.base import BaseRetriever
from app.schemas import Document

logger = logging.getLogger(__name__)


class CrossEncoderReranker(BaseRetriever):
    def __init__(
        self,
        base_retriever: BaseRetriever,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        top_n: int = 5,
    ):
        self._base = base_retriever
        self._model_name = model_name
        self._top_n = max(1, top_n)
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            logger.info("Loading cross-encoder model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name, max_length=512)
            logger.info("Cross-encoder model loaded successfully")
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for cross-encoder reranking. "
                "Run: pip install sentence-transformers"
            )

    def _rerank(self, query: str, docs: List[Document]) -> List[Document]:
        if not docs:
            return docs

        self._load_model()
        pairs = [(query, doc.content[:512]) for doc in docs]
        scores = self._model.predict(pairs)
        scored_docs = list(zip(docs, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored_docs[: self._top_n]]

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        candidate_k = max(top_k, self._top_n)
        docs = self._base.retrieve(query=query, top_k=candidate_k)
        if not docs:
            return []
        return self._rerank(query, docs)[:top_k]

    def get_docs_by_ids(self, ids: List[str]) -> List[Document]:
        return self._base.get_docs_by_ids(ids=ids)
