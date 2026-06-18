from typing import List, Tuple

from app.llm_client import LLMClient
from app.retrievers.base import BaseRetriever
from app.schemas import Document

GRADE_SYSTEM_PROMPT = """你是文档相关性评估器。判断给定文档是否与用户问题相关。

规则：
1. 仔细阅读文档内容和用户问题
2. 判断文档是否包含回答问题所需的信息
3. 对每个文档输出评分：correct（直接相关）、incorrect（不相关）、ambiguous（部分相关或信息不足）
4. 只输出评分结果，格式为每行一个：文档序号|评分
5. 示例：
1|correct
2|incorrect
3|ambiguous"""

REWRITE_PROMPT = """你是查询改写器。原始查询检索效果不佳，请生成一个替代查询以获取更多相关信息。

规则：
1. 保持原始意图不变
2. 尝试用不同的关键词或表述方式
3. 只输出改写后的查询，不要解释"""


def _parse_grades(raw: str, expected_count: int) -> List[str]:
    grades: List[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            grade = parts[1].strip().lower()
            if grade in {"correct", "incorrect", "ambiguous"}:
                grades.append(grade)
    while len(grades) < expected_count:
        grades.append("ambiguous")
    return grades[:expected_count]


class CRAGRetriever(BaseRetriever):
    def __init__(
        self,
        base_retriever: BaseRetriever,
        llm_client: LLMClient,
        max_retries: int = 1,
        correct_threshold: float = 0.5,
    ):
        self._base = base_retriever
        self._llm_client = llm_client
        self._max_retries = max(1, max_retries)
        self._correct_threshold = max(0.0, min(1.0, correct_threshold))

    def _grade_docs(self, query: str, docs: List[Document]) -> List[str]:
        doc_texts = []
        for idx, doc in enumerate(docs, start=1):
            content = doc.content[:500] if len(doc.content) > 500 else doc.content
            doc_texts.append(f"[{idx}] {content}")

        user_msg = (
            f"用户问题：{query}\n\n"
            f"检索到的文档：\n" + "\n\n".join(doc_texts) + "\n\n"
            "请对每个文档评分（correct/incorrect/ambiguous）。"
        )

        messages = [
            {"role": "system", "content": GRADE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        try:
            raw = self._llm_client.chat(messages=messages, temperature=0.0)
        except Exception:
            return ["ambiguous"] * len(docs)

        return _parse_grades(raw, len(docs))

    def _rewrite_query(self, query: str) -> str:
        messages = [
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": f"原始查询：{query}"},
        ]
        try:
            rewritten = self._llm_client.chat(messages=messages, temperature=0.3)
            rewritten = rewritten.strip().strip("\"' ")
            return rewritten if rewritten else query
        except Exception:
            return query

    def _filter_by_grades(
        self, docs: List[Document], grades: List[str]
    ) -> Tuple[List[Document], List[Document]]:
        correct_docs: List[Document] = []
        ambiguous_docs: List[Document] = []

        for doc, grade in zip(docs, grades):
            if grade == "correct":
                correct_docs.append(doc)
            elif grade == "ambiguous":
                ambiguous_docs.append(doc)

        return correct_docs, ambiguous_docs

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        current_query = query
        best_docs: List[Document] = []

        for attempt in range(self._max_retries + 1):
            docs = self._base.retrieve(query=current_query, top_k=top_k)
            if not docs:
                break

            grades = self._grade_docs(current_query, docs)
            correct_docs, ambiguous_docs = self._filter_by_grades(docs, grades)

            usable = correct_docs + ambiguous_docs
            if len(usable) >= top_k or attempt == self._max_retries:
                best_docs = usable[:top_k]
                break

            correct_ratio = len(correct_docs) / max(1, len(docs))
            if correct_ratio < self._correct_threshold:
                current_query = self._rewrite_query(current_query)
            else:
                best_docs = usable[:top_k]
                break

        if not best_docs:
            best_docs = self._base.retrieve(query=query, top_k=top_k)

        return best_docs

    def get_docs_by_ids(self, ids: List[str]) -> List[Document]:
        return self._base.get_docs_by_ids(ids=ids)
