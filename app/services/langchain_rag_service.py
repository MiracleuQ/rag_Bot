import re
import threading
import time
from collections import OrderedDict
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

HISTORY_REWRITE_SYSTEM_PROMPT = """你是企业知识库检索查询改写器。结合历史对话，把用户当前追问改写成可以独立检索的完整问题。
要求：
1. 如果当前问题已经完整清晰，原样输出；
2. 保留原意，不补充未经提供的事实；
3. 只输出改写后的问题文本，不添加任何解释。"""

_HISTORY_REWRITE_PREFIX_RE = re.compile(r"^(改写后|改写问题|检索问题|问题)\s*[:：]\s*")
_FOLLOW_UP_HINT_RE = re.compile(
    r"(\u8fd9\u4e2a|\u90a3\u4e2a|\u4e0a\u4e00\u6b65|\u4e0b\u4e00\u6b65|\u7ee7\u7eed|\u7136\u540e|\u521a\u624d|\u4e0a\u9762|\u4e0a\u8ff0|\u5982\u4f55|\u7b2c\u4e8c\u6b65|\u7b2c\u4e09\u6b65)"
)
_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_ENUM_QUERY_HINT_RE = re.compile(
    r"(\u6709\u54ea|\u54ea\u4e9b|\u6709\u4ec0\u4e48|\u5168\u90e8|\u6240\u6709|\u5b8c\u6574|\u6e05\u5355|\u5217\u8868|\u5217\u51fa|\u76f8\u5173\u6d41\u7a0b)"
)
_FLOW_ENUM_QUERY_HINT_RE = re.compile(
    r"(\u76f8\u5173\u6d41\u7a0b|\u6d41\u7a0b.*(\u6709\u54ea|\u5305\u62ec|\u5217\u51fa)|\u6709\u54ea.*\u6d41\u7a0b)"
)
_FLOW_HEADING_RE = re.compile(r"(?<![\d.])(\d+\.\d+)(?!\.\d)\s*([^\n]{1,80})")
_FLOW_SUB_HEADING_RE = re.compile(r"(?<![\d.])(\d+\.\d+\.\d+)(?!\.\d)\s*([^\n]{1,120})")


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


def _tokenize_for_coverage(text: str) -> Set[str]:
    normalized = text.lower().strip()
    if not normalized:
        return set()
    tokens = set(_TOKEN_RE.findall(normalized))
    chinese_chars = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
    if len(chinese_chars) == 1:
        tokens.add(chinese_chars[0])
    for idx in range(0, max(len(chinese_chars) - 1, 0)):
        tokens.add("".join(chinese_chars[idx : idx + 2]))
    return {token for token in tokens if token}


def _coverage_score(query: str, docs: Sequence[Document]) -> float:
    query_tokens = _tokenize_for_coverage(query)
    if not query_tokens:
        return 0.0
    merged_text = " ".join(doc.content for doc in docs[:3] if doc.content)
    if not merged_text.strip():
        return 0.0
    hit_count = len(query_tokens.intersection(_tokenize_for_coverage(merged_text)))
    return hit_count / max(1, len(query_tokens))


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

        try:
            all_results = self._retriever._collection.get(
                ids=parent_ids,
                include=["documents", "metadatas"],
            )
        except Exception:
            return docs

        parent_docs: List[Document] = []
        raw_ids = all_results.get("ids", [])
        raw_docs = all_results.get("documents", [])
        raw_metas = all_results.get("metadatas", [])

        for idx, pid in enumerate(raw_ids):
            content = str(raw_docs[idx] if idx < len(raw_docs) else "").strip()
            meta = raw_metas[idx] if idx < len(raw_metas) else {}
            source = str(meta.get("source_path", "")) if meta else ""
            parent_docs.append(
                Document(doc_id=pid, content=content, source=source, score=None)
            )

        return parent_docs if parent_docs else docs

    def _build_structured_answer(
        self, question: str, docs: List[Document], output_format: str
    ) -> str:
        if output_format == OutputFormat.DEFAULT:
            return ""

        context = _format_context(docs)
        system_prompt = get_system_prompt(output_format)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{retrieval_prompt}"),
            ]
        )
        chain = (
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
        if _FLOW_ENUM_QUERY_HINT_RE.search(question.strip()):
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
        coverage = _coverage_score(query, docs)
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

        best_docs: List[Document] = []
        best_rank = (0, float("-inf"), 0.0, float("-inf"))
        for query in candidates:
            docs = self._retrieve_docs_by_query(query, top_k=retrieval_top_k)
            rank = self._rank_retrieval(query, docs)
            if rank > best_rank:
                best_rank = rank
                best_docs = docs
        return best_docs

    @staticmethod
    def _load_source_text_for_flow(source_path: str) -> str:
        path = Path(str(source_path or "")).expanduser()
        if not path.exists() or not path.is_file():
            return ""

        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                pages = [(page.extract_text() or "").strip() for page in reader.pages]
                return "\n".join(text for text in pages if text)
            if suffix in {".txt", ".md", ".csv", ".log", ".json"}:
                return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
        return ""

    @staticmethod
    def _is_flow_enumeration_question(question: str) -> bool:
        return bool(_FLOW_ENUM_QUERY_HINT_RE.search(question.strip()))

    @staticmethod
    def _flow_code_key(code: str) -> tuple[int, ...]:
        parts = []
        for seg in code.split("."):
            try:
                parts.append(int(seg))
            except ValueError:
                parts.append(9999)
        return tuple(parts)

    @staticmethod
    def _clean_heading_title(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip(" ：:;；。 \t\r\n")).strip()

    @staticmethod
    def _clean_detail_text(text: str, max_len: int = 48) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        normalized = re.sub(
            r"(\[Page\s*\d+\]|\u6587\u4ef6\u7f16\u53f7\s*WI-[A-Z]{2}-\d+|\u4fee\u6539\u7248\u6b21.*?\u9875)",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip(" ：:;；。 \t\r\n")
        if len(normalized) > max_len:
            normalized = normalized[:max_len].rstrip(" ，,;；")
        return normalized

    @staticmethod
    def _shorten_clause(text: str, target_len: int = 22, max_len: int = 40) -> str:
        content = str(text or "").strip()
        if not content:
            return ""

        first_sentence = re.split(r"[。；;]", content)[0].strip()
        comma_parts = [p.strip() for p in re.split(r"[，,]", first_sentence) if p.strip()]
        if not comma_parts:
            candidate = first_sentence
        else:
            candidate = comma_parts[0]
            for part in comma_parts[1:]:
                if len(candidate) >= target_len:
                    break
                trial = f"{candidate}，{part}"
                if len(trial) > max_len:
                    break
                candidate = trial
        if len(candidate) > max_len:
            candidate = candidate[:max_len]
        return candidate.strip(" ：:;；。 \t\r\n")

    @staticmethod
    def _extract_flow_details(section_text: str, major_code: str) -> List[str]:
        if not section_text.strip():
            return []

        details: List[str] = []
        seen = set()
        sub_matches = list(_FLOW_SUB_HEADING_RE.finditer(section_text))
        for idx, sub_match in enumerate(sub_matches):
            sub_code = sub_match.group(1).strip()
            if not sub_code.startswith(f"{major_code}."):
                continue

            next_start = len(section_text)
            for follow in sub_matches[idx + 1 :]:
                next_start = follow.start()
                break

            block = section_text[sub_match.start() : next_start]
            block = re.sub(rf"^\s*{re.escape(sub_code)}\s*", "", block.strip())
            sub_title = LangChainRAGService._clean_heading_title(sub_match.group(2))
            sub_title = re.split(r"(?<![\d.])\d+\.\d+\.\d+(?!\.\d)", sub_title, maxsplit=1)[0]
            if not sub_title:
                sentence = re.split(r"[。；;]", block)[0]
                sub_title = sentence
            sub_title = LangChainRAGService._clean_detail_text(sub_title, max_len=96)
            for sep in ("，", ",", "：", ":"):
                if sep in sub_title:
                    prefix = sub_title.split(sep, 1)[0].strip()
                    if len(prefix) >= 10:
                        sub_title = prefix
                    break
            sub_title = LangChainRAGService._clean_detail_text(sub_title, max_len=96)
            sub_title = LangChainRAGService._shorten_clause(sub_title, target_len=22, max_len=40)
            if not sub_title or sub_title in seen:
                continue
            seen.add(sub_title)
            details.append(sub_title)
            if len(details) >= 2:
                return details

        normalized = re.sub(r"\s+", " ", section_text).strip()
        reference_match = re.search(r"(详见《[^》]+》)", normalized)
        if reference_match:
            ref = LangChainRAGService._clean_detail_text(reference_match.group(1), max_len=30)
            if ref and ref not in seen:
                details.append(ref)
                return details
        for sentence in re.split(r"[。；;]", normalized):
            clean = LangChainRAGService._clean_detail_text(sentence, max_len=96)
            clean = LangChainRAGService._shorten_clause(clean, target_len=22, max_len=40)
            if len(clean) < 8:
                continue
            if clean in seen:
                continue
            seen.add(clean)
            details.append(clean)
            if len(details) >= 2:
                break
        return details

    @staticmethod
    def _build_flow_enumeration_answer(question: str, docs: Sequence[Document]) -> str:
        if not docs or not LangChainRAGService._is_flow_enumeration_question(question):
            return ""

        by_source: OrderedDict[str, List[Document]] = OrderedDict()
        for doc in docs:
            source = (doc.source or "").strip()
            if not source:
                continue
            by_source.setdefault(source, []).append(doc)
        if not by_source:
            return ""

        dominant_source = sorted(
            by_source.items(),
            key=lambda item: (
                len(item[1]),
                max(
                    [float(d.score) for d in item[1] if isinstance(d.score, (int, float))]
                    or [float("-inf")]
                ),
            ),
            reverse=True,
        )[0][0]

        merged_text = "\n".join(doc.content for doc in by_source[dominant_source] if doc.content.strip())
        source_text = LangChainRAGService._load_source_text_for_flow(dominant_source)
        heading_source_text = source_text.strip() or merged_text.strip()
        if not heading_source_text:
            return ""

        heading_matches = []
        for match in _FLOW_HEADING_RE.finditer(heading_source_text):
            code = match.group(1).strip()
            title = LangChainRAGService._clean_heading_title(match.group(2))
            if not code or not title:
                continue
            if not code.startswith("4."):
                continue
            heading_matches.append(
                {
                    "code": code,
                    "title": title,
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        if not heading_matches:
            return ""

        # 按流程编码去重，优先保留更短更像标题的文本。
        heading_map: OrderedDict[str, dict] = OrderedDict()
        for item in heading_matches:
            existed = heading_map.get(item["code"])
            if not existed or len(str(item["title"])) < len(str(existed["title"])):
                heading_map[item["code"]] = item

        flow_items = sorted(
            [(code, data["title"]) for code, data in heading_map.items()],
            key=lambda x: LangChainRAGService._flow_code_key(x[0]),
        )
        if len(flow_items) < 3:
            return ""

        heading_by_code = {code: heading_map[code] for code, _ in flow_items if code in heading_map}
        source_title = Path(dominant_source).stem or dominant_source
        lines = [f"根据《{source_title}》，相关流程包括：", ""]
        for idx, (code, title) in enumerate(flow_items):
            current = heading_by_code.get(code)
            if not current:
                lines.append(f"- {title}")
                continue
            next_start = len(heading_source_text)
            for follow_code, _ in flow_items[idx + 1 :]:
                follow = heading_by_code.get(follow_code)
                if follow and isinstance(follow.get("start"), int):
                    next_start = int(follow["start"])
                    break
            section_text = heading_source_text[int(current["end"]) : next_start]
            details = LangChainRAGService._extract_flow_details(section_text=section_text, major_code=code)
            if details:
                lines.append(f"- {title}：{details[0]}；{details[1]}" if len(details) > 1 else f"- {title}：{details[0]}")
            else:
                lines.append(f"- {title}")
        return "\n".join(lines).strip()

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
        flow_answer = self._build_flow_enumeration_answer(
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
