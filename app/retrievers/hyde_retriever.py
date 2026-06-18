import logging
from typing import List

from app.llm_client import LLMClient
from app.retrievers.base import BaseRetriever
from app.schemas import Document

logger = logging.getLogger(__name__)

_HYDE_SYSTEM_PROMPT = """你是一个文档生成器。根据用户的问题，生成一段假设性的文档内容来回答该问题。
要求：
1. 生成的内容应该像真实的企业文档片段
2. 使用正式的中文书面语
3. 内容应该包含与问题相关的关键信息
4. 长度控制在 200-400 字
5. 只输出文档内容，不要添加任何解释或标题"""


class HyDERetriever(BaseRetriever):
    def __init__(
        self,
        base_retriever: BaseRetriever,
        llm_client: LLMClient,
        enabled: bool = True,
    ):
        self._base = base_retriever
        self._llm_client = llm_client
        self._enabled = enabled

    def _generate_hypothetical_doc(self, query: str) -> str:
        messages = [
            {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
            {"role": "user", "content": f"问题：{query}"},
        ]
        try:
            response = self._llm_client.chat(messages=messages, temperature=0.7)
            return response.strip()
        except Exception as exc:
            logger.warning("HyDE generation failed: %s", exc)
            return ""

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        if not self._enabled or not query.strip():
            return self._base.retrieve(query=query, top_k=top_k)

        hypothetical = self._generate_hypothetical_doc(query)
        if not hypothetical:
            return self._base.retrieve(query=query, top_k=top_k)

        hyde_docs = self._base.retrieve(query=hypothetical, top_k=top_k)
        original_docs = self._base.retrieve(query=query, top_k=top_k)

        seen_ids = set()
        merged: List[Document] = []
        for doc in hyde_docs + original_docs:
            if doc.doc_id not in seen_ids:
                seen_ids.add(doc.doc_id)
                merged.append(doc)
        return merged[:top_k]

    def get_docs_by_ids(self, ids: List[str]) -> List[Document]:
        return self._base.get_docs_by_ids(ids=ids)
