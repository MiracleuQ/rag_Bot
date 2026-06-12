from typing import List

from langchain_core.documents import Document as LCDocument
from langchain_core.retrievers import BaseRetriever as LCBaseRetriever
from pydantic import ConfigDict

from app.retrievers.base import BaseRetriever as AppBaseRetriever
from app.schemas import Document as AppDocument


def _to_lc_document(doc: AppDocument) -> LCDocument:
    metadata = {"doc_id": doc.doc_id, "source": doc.source or ""}
    if doc.score is not None:
        metadata["score"] = float(doc.score)
    return LCDocument(
        page_content=doc.content,
        metadata=metadata,
    )


class LangChainRetrieverAdapter(LCBaseRetriever):
    """
    Adapter so existing retriever implementations can be plugged into
    LangChain LCEL without changing storage-layer code.
    """

    source_retriever: AppBaseRetriever
    top_k: int = 3
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(self, query: str, **_: object) -> List[LCDocument]:
        docs = self.source_retriever.retrieve(query=query, top_k=self.top_k)
        return [_to_lc_document(doc) for doc in docs if doc.content.strip()]
