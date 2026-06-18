import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, List, Mapping, Sequence, Set, Tuple

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from app.llm_client import LLMClient
from app.prompts import (
    NO_KB_HIT_MESSAGE,
    SENSITIVE_BLOCK_MESSAGE,
    SYSTEM_PROMPT,
    OutputFormat,
    build_user_prompt,
    detect_output_format,
    get_system_prompt,
)
from app.query_rewrite.base import BaseQueryRewriter
from app.query_rewrite.noop import NoopQueryRewriter
from app.retrievers.base import BaseRetriever
from app.schemas import ChatResponse, Document
from app.security.sensitive import is_sensitive_question
from app.services.flow_enumerator import build_flow_enumeration_answer, is_flow_enumeration_question
from app.utils import coverage_score

HISTORY_REWRITE_SYSTEM_PROMPT = """你是企业知识库检索查询改写器。结合历史对话，把用户当前追问改写成可以独立检索的完整问题。
要求：
1. 如果当前问题已经完整清晰，原样输出；
2. 保留原意，不补充未经提供的事实；
3. 只输出改写后的问题文本，不添加任何解释。"""

_HISTORY_REWRITE_PREFIX_RE = re.compile(r"^(改写后|改写问题|检索问题|问题)\s*[:：]\s*")
_FOLLOW_UP_HINT_RE = re.compile(
    r"(\u8fd9\u4e2a|\u90a3\u4e2a|\u4e0a\u4e00\u6b65|\u4e0b\u4e00\u6b65|\u7ee7\u7eed|\u7136\u540e|\u521a\u624d|\u4e0a\u9762|\u4e0a\u8ff0|\u5982\u4f55|\u7b2c\u4e8c\u6b65|\u7b2c\u4e09\u6b65)"
)
_ENUM_QUERY_HINT_RE = re.compile(
    r"(\u6709\u54ea|\u54ea\u4e9b|\u6709\u4ec0\u4e48|\u5168\u90e8|\u6240\u6709|\u5b8c\u6574|\u6e05\u5355|\u5217\u8868|\u5217\u51fa|\u76f8\u5173\u6d41\u7a0b)"
)


class _SessionQueryRewriteCache:
    def __init__(self, enabled: bool, ttl_sec: int, max_size: int):
        self._enabled = bool(enabled)
        self._ttl_sec = max(1, int(ttl_sec))
        self._max_size = max(1, int(max_size))
        self._values: OrderedDict[str, Tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        if not self._enabled:
            return None
        now = time.monotonic()
        with self._lock:
            value = self._values.get(key)
            if not value:
                return None
            expires_at, payload = value
            if expires_at <= now:
                self._values.pop(key, None)
                return None
            self._values.move_to_end(key)
            return payload

    def put(self, key: str, value: str) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        with self._lock:
            self._values[key] = (now + self._ttl_sec, value)
            self._values.move_to_end(key)
            stale_keys = [k for k, (expires_at, _) in self._values.items() if expires_at <= now]
            for stale_key in stale_keys:
                self._values.pop(stale_key, None)
            while len(self._values) > self._max_size:
                self._values.popitem(last=False)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _to_openai_messages(messages: List[BaseMessage]) -> List[dict]:
    role_map = {
        "system": "system",
        "human": "user",
        "ai": "assistant",
        "assistant": "assistant",
        "user": "user",
    }
    converted = []
    for message in messages:
        role = role_map.get(message.type, "user")
        converted.append({"role": role, "content": _content_to_text(message.content)})
    return converted


def _format_context(docs: List[Document]) -> str:
    chunks = []
    for idx, doc in enumerate(docs, start=1):
        source = doc.source or "unknown"
        chunks.append(f"[{idx}] source={source}\n{doc.content}")
    return "\n\n".join(chunks)


def _normalize_doc_key(doc: Document) -> str:
    source = (doc.source or "").strip()
    doc_id = (doc.doc_id or "").strip()
    if source:
        normalized = source.replace("\\", "/")
        filename = Path(normalized).name.strip()
        if filename:
            return f"source:{filename.lower()}"
        return f"source:{normalized.lower()}"
    return f"doc:{doc_id.replace('\\', '/').lower()}"


def _to_doc_level_citations(docs: Sequence[Document]) -> List[Document]:
    unique_docs: List[Document] = []
    seen: Set[str] = set()

    for idx, doc in enumerate(docs, start=1):
        key = _normalize_doc_key(doc)
        if not key:
            key = f"unknown:{idx}"
        if key in seen:
            continue
        seen.add(key)

        source = (doc.source or "").strip() or None
        doc_id = (doc.doc_id or "").strip() or (source or f"doc-{idx}")
        unique_docs.append(
            Document(
                doc_id=doc_id,
                source=source,
                content="",
                score=doc.score if isinstance(doc.score, (int, float)) else None,
            )
        )
    return unique_docs


def _sanitize_rewritten_query(text: str) -> str:
    lines = (text or "").strip().splitlines()
    first_line = lines[0].strip() if lines else ""
    first_line = _HISTORY_REWRITE_PREFIX_RE.sub("", first_line).strip()
    return first_line.strip("\"' ")


def _is_follow_up_question(question: str) -> bool:
    clean = question.strip()
    if not clean:
        return False
    if len(clean) <= 6:
        return True
    return bool(_FOLLOW_UP_HINT_RE.search(clean))


def _format_history_turns(history_messages: Sequence[Mapping[str, str]]) -> str:
    lines: List[str] = []
    for item in history_messages:
        role = str(item.get("role", "")).lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"用户: {content}")
        elif role == "assistant":
            lines.append(f"助手: {content}")
    return "\n".join(lines)


def _latest_user_message(history_messages: Sequence[Mapping[str, str]]) -> str:
    for item in reversed(history_messages):
        role = str(item.get("role", "")).lower()
        content = str(item.get("content", "")).strip()
        if role == "user" and content:
            return content
    return ""


class LangChainRAGService:
    def __init__(
        self,
        retriever: BaseRetriever,
        llm_client: LLMClient,
        top_k: int = 3,
        query_rewriter: BaseQueryRewriter | None = None,
        enable_history_question_rewrite: bool = True,
        enable_dual_route_retrieval: bool = True,
        query_rewrite_cache_enabled: bool = True,
        query_rewrite_cache_ttl_sec: int = 900,
        query_rewrite_cache_max_size: int = 512,
        enable_structured_output: bool = True,
    ):
        self._retriever = retriever
        self._llm_client = llm_client
        self._top_k = top_k
        self._query_rewriter = query_rewriter or NoopQueryRewriter()
        self._enable_history_question_rewrite = enable_history_question_rewrite
        self._enable_dual_route_retrieval = enable_dual_route_retrieval
        self._enable_structured_output = enable_structured_output
        self._query_rewrite_cache = _SessionQueryRewriteCache(
            enabled=query_rewrite_cache_enabled,
            ttl_sec=query_rewrite_cache_ttl_sec,
            max_size=query_rewrite_cache_max_size,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "{retrieval_prompt}"),
            ]
        )
        self._generation_chain = (
            RunnableLambda(
                lambda x: {
                    "retrieval_prompt": build_user_prompt(
                        question=x["question"],
                        context=x["context"],
                    )
                }
            )
            | prompt
            | RunnableLambda(self._invoke_llm_from_prompt)
        )

        self._structured_chains: dict[str, Any] = {}
        for fmt in (OutputFormat.TABLE, OutputFormat.LIST):
            fmt_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", get_system_prompt(fmt)),
                    ("human", "{retrieval_prompt}"),
                ]
            )
            self._structured_chains[fmt] = (
                RunnableLambda(
                    lambda x: {
                        "retrieval_prompt": build_user_prompt(
                            question=x["question"],
                            context=x["context"],
                        )
                    }
                )
                | fmt_prompt
                | RunnableLambda(self._invoke_llm_from_prompt)
            )

    def _resolve_parent_chunks(self, docs: List[Document]) -> List[Document]:
        parent_ids: List[str] = []
        seen_parents: set[str] = set()
        for doc in docs:
            parent_id = None
            if hasattr(doc, "_parent_chunk_id"):
                parent_id = doc._parent_chunk_id
            elif hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
                parent_id = doc.metadata.get("parent_chunk_id")
            if parent_id and parent_id not in seen_parents:
                parent_ids.append(parent_id)
                seen_parents.add(parent_id)

        if not parent_ids:
            return docs

        parent_docs = self._retriever.get_docs_by_ids(ids=parent_ids)
        return parent_docs if parent_docs else docs

    def _build_structured_answer(
        self, question: str, docs: List[Document], output_format: str
    ) -> str:
        if output_format == OutputFormat.DEFAULT:
            return ""

        chain = self._structured_chains.get(output_format)
        if chain is None:
            return ""

        context = _format_context(docs)
        try:
            return chain.invoke({"question": question, "context": context}).strip()
        except Exception:
            return ""

    def _invoke_llm_from_prompt(self, prompt_value: Any) -> str:
        messages = _to_openai_messages(list(prompt_value.messages))
        return self._llm_client.chat(messages=messages)

    def _rewrite_question_from_history(
        self,
        question: str,
        history_messages: Sequence[Mapping[str, str]] | None,
    ) -> str:
        original = question.strip()
        if not original:
            return ""
        if not self._enable_history_question_rewrite:
            return original
        if not history_messages:
            return original
        if not _is_follow_up_question(original):
            return original

        history_text = _format_history_turns(history_messages)
        if not history_text:
            return original

        messages = [
            {"role": "system", "content": HISTORY_REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"历史对话：\n{history_text}\n\n"
                    f"当前问题：\n{original}\n\n"
                    "请输出改写后的完整检索问题。"
                ),
            },
        ]
        try:
            rewritten = self._llm_client.chat(messages=messages, temperature=0.0)
        except Exception:
            rewritten = ""

        rewritten = _sanitize_rewritten_query(rewritten)
        if rewritten:
            return rewritten

        latest_user = _latest_user_message(history_messages)
        if latest_user and latest_user != original:
            return f"{latest_user}；补充问题：{original}"
        return original

    def _rewrite_query_with_cache(self, standalone_question: str, session_id: str | None) -> str:
        question = standalone_question.strip()
        if not question:
            return ""
        cache_key = f"{self._query_rewriter.__class__.__name__}|{session_id or '_'}|{question}"
        cached = self._query_rewrite_cache.get(cache_key)
        if cached is not None:
            return cached

        rewritten = self._query_rewriter.rewrite(question) or question
        self._query_rewrite_cache.put(cache_key, rewritten)
        return rewritten

    def _resolve_retrieval_top_k(self, question: str) -> int:
        base_top_k = max(1, int(self._top_k))
        if is_flow_enumeration_question(question):
            return max(base_top_k, 12)
        if _ENUM_QUERY_HINT_RE.search(question.strip()):
            return max(base_top_k, min(12, base_top_k * 2))
        return base_top_k

    def _retrieve_docs_by_query(self, query: str, top_k: int) -> List[Document]:
        return self._retriever.retrieve(query=query, top_k=max(1, int(top_k)))

    @staticmethod
    def _rank_retrieval(query: str, docs: Sequence[Document]) -> Tuple[int, float, float, float]:
        if not docs:
            return (0, float("-inf"), 0.0, float("-inf"))
        scores = [float(doc.score) for doc in docs if isinstance(doc.score, (int, float))]
        max_score = max(scores) if scores else float("-inf")
        avg_score = (sum(scores) / len(scores)) if scores else float("-inf")
        merged_text = " ".join(doc.content for doc in docs[:3] if doc.content)
        coverage = coverage_score(query, merged_text)
        return (len(docs), max_score, coverage, avg_score)

    def _retrieve_best_docs(
        self,
        question: str,
        standalone_question: str,
        retrieval_query: str,
        retrieval_top_k: int,
    ) -> List[Document]:
        candidates: List[str] = []
        seen_queries = set()
        for raw_query in [retrieval_query, standalone_question, question]:
            query = raw_query.strip()
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            candidates.append(query)

        if len(candidates) <= 1:
            query = candidates[0] if candidates else ""
            return self._retrieve_docs_by_query(query, top_k=retrieval_top_k) if query else []

        all_results: List[Tuple[str, List[Document]]] = []
        with ThreadPoolExecutor(max_workers=min(len(candidates), 3)) as executor:
            future_to_query = {
                executor.submit(self._retrieve_docs_by_query, query, retrieval_top_k): query
                for query in candidates
            }
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    docs = future.result()
                except Exception:
                    docs = []
                if docs:
                    all_results.append((query, docs))

        if not all_results:
            return []

        if len(all_results) == 1:
            return all_results[0][1]

        return self._rrf_fusion(all_results, top_k=retrieval_top_k)

    @staticmethod
    def _rrf_fusion(
        all_results: List[Tuple[str, List[Document]]],
        top_k: int,
        k: int = 60,
    ) -> List[Document]:
        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}
        for _, docs in all_results:
            for rank, doc in enumerate(docs):
                key = f"{doc.doc_id}|{doc.content[:100]}"
                rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
                if key not in doc_map:
                    doc_map[key] = doc

        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        return [doc_map[key] for key in sorted_keys[:top_k]]

    def answer(
        self,
        question: str,
        history_messages: Sequence[Mapping[str, str]] | None = None,
        session_id: str | None = None,
    ) -> ChatResponse:
        if is_sensitive_question(question):
            return ChatResponse(answer=SENSITIVE_BLOCK_MESSAGE, used_docs=[])

        standalone_question = self._rewrite_question_from_history(
            question=question,
            history_messages=history_messages,
        )
        retrieval_query = self._rewrite_query_with_cache(
            standalone_question=standalone_question,
            session_id=session_id,
        )
        retrieval_top_k = self._resolve_retrieval_top_k(question=standalone_question)

        if self._enable_dual_route_retrieval:
            docs = self._retrieve_best_docs(
                question=question,
                standalone_question=standalone_question,
                retrieval_query=retrieval_query,
                retrieval_top_k=retrieval_top_k,
            )
        else:
            docs = self._retrieve_docs_by_query(retrieval_query, top_k=retrieval_top_k)
            if not docs and retrieval_query != standalone_question:
                docs = self._retrieve_docs_by_query(standalone_question, top_k=retrieval_top_k)
            if not docs and standalone_question != question:
                docs = self._retrieve_docs_by_query(question, top_k=retrieval_top_k)

        if not docs:
            return ChatResponse(answer=NO_KB_HIT_MESSAGE, used_docs=[])

        docs = self._resolve_parent_chunks(docs)

        citation_docs = _to_doc_level_citations(docs)
        flow_answer = build_flow_enumeration_answer(
            question=standalone_question,
            docs=docs,
        )
        if flow_answer:
            return ChatResponse(answer=flow_answer, used_docs=citation_docs)

        output_format = (
            detect_output_format(standalone_question)
            if self._enable_structured_output
            else OutputFormat.DEFAULT
        )

        if output_format != OutputFormat.DEFAULT:
            structured = self._build_structured_answer(
                question=standalone_question,
                docs=docs,
                output_format=output_format,
            )
            if structured:
                return ChatResponse(answer=structured, used_docs=citation_docs)

        context = _format_context(docs)
        answer = self._generation_chain.invoke(
            {"question": standalone_question, "context": context}
        ).strip()
        if not answer:
            answer = NO_KB_HIT_MESSAGE

        return ChatResponse(answer=answer, used_docs=citation_docs)
