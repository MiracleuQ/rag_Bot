import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import List, Sequence

from app.schemas import Document

_FLOW_ENUM_QUERY_HINT_RE = re.compile(
    r"(\u76f8\u5173\u6d41\u7a0b|\u6d41\u7a0b.*(\u6709\u54ea|\u5305\u62ec|\u5217\u51fa)|\u6709\u54ea.*\u6d41\u7a0b)"
)
_FLOW_HEADING_RE = re.compile(r"(?<![\d.])(\d+\.\d+)(?!\.\d)\s*([^\n]{1,80})")
_FLOW_SUB_HEADING_RE = re.compile(r"(?<![\d.])(\d+\.\d+\.\d+)(?!\.\d)\s*([^\n]{1,120})")

_SOURCE_TEXT_CACHE_MAX_SIZE = 32
_source_text_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_source_text_cache_lock = threading.Lock()


def _load_source_text(source_path: str) -> str:
    path = Path(str(source_path or "")).expanduser()
    if not path.exists() or not path.is_file():
        return ""

    cache_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""

    with _source_text_cache_lock:
        cached = _source_text_cache.get(cache_key)
        if cached and cached[0] == mtime:
            _source_text_cache.move_to_end(cache_key)
            return cached[1]

    suffix = path.suffix.lower()
    text = ""
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
            text = "\n".join(t for t in pages if t)
        elif suffix in {".txt", ".md", ".csv", ".log", ".json"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""

    with _source_text_cache_lock:
        _source_text_cache[cache_key] = (mtime, text)
        _source_text_cache.move_to_end(cache_key)
        while len(_source_text_cache) > _SOURCE_TEXT_CACHE_MAX_SIZE:
            _source_text_cache.popitem(last=False)

    return text


def _flow_code_key(code: str) -> tuple[int, ...]:
    parts = []
    for seg in code.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(9999)
    return tuple(parts)


def _clean_heading_title(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip(" ：:;；。 \t\r\n")).strip()


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
        for follow in sub_matches[idx + 1:]:
            next_start = follow.start()
            break

        block = section_text[sub_match.start(): next_start]
        block = re.sub(rf"^\s*{re.escape(sub_code)}\s*", "", block.strip())
        sub_title = _clean_heading_title(sub_match.group(2))
        sub_title = re.split(r"(?<![\d.])\d+\.\d+\.\d+(?!\.\d)", sub_title, maxsplit=1)[0]
        if not sub_title:
            sentence = re.split(r"[。；;]", block)[0]
            sub_title = sentence
        sub_title = _clean_detail_text(sub_title, max_len=96)
        for sep in ("，", ",", "：", ":"):
            if sep in sub_title:
                prefix = sub_title.split(sep, 1)[0].strip()
                if len(prefix) >= 10:
                    sub_title = prefix
                break
        sub_title = _clean_detail_text(sub_title, max_len=96)
        sub_title = _shorten_clause(sub_title, target_len=22, max_len=40)
        if not sub_title or sub_title in seen:
            continue
        seen.add(sub_title)
        details.append(sub_title)
        if len(details) >= 2:
            return details

    normalized = re.sub(r"\s+", " ", section_text).strip()
    reference_match = re.search(r"(详见《[^》]+》)", normalized)
    if reference_match:
        ref = _clean_detail_text(reference_match.group(1), max_len=30)
        if ref and ref not in seen:
            details.append(ref)
            return details
    for sentence in re.split(r"[。；;]", normalized):
        clean = _clean_detail_text(sentence, max_len=96)
        clean = _shorten_clause(clean, target_len=22, max_len=40)
        if len(clean) < 8:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        details.append(clean)
        if len(details) >= 2:
            break
    return details


def is_flow_enumeration_question(question: str) -> bool:
    return bool(_FLOW_ENUM_QUERY_HINT_RE.search(question.strip()))


def build_flow_enumeration_answer(question: str, docs: Sequence[Document]) -> str:
    if not docs or not is_flow_enumeration_question(question):
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
    source_text = _load_source_text(dominant_source)
    heading_source_text = source_text.strip() or merged_text.strip()
    if not heading_source_text:
        return ""

    heading_matches = []
    for match in _FLOW_HEADING_RE.finditer(heading_source_text):
        code = match.group(1).strip()
        title = _clean_heading_title(match.group(2))
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

    heading_map: OrderedDict[str, dict] = OrderedDict()
    for item in heading_matches:
        existed = heading_map.get(item["code"])
        if not existed or len(str(item["title"])) < len(str(existed["title"])):
            heading_map[item["code"]] = item

    flow_items = sorted(
        [(code, data["title"]) for code, data in heading_map.items()],
        key=lambda x: _flow_code_key(x[0]),
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
        for follow_code, _ in flow_items[idx + 1:]:
            follow = heading_by_code.get(follow_code)
            if follow and isinstance(follow.get("start"), int):
                next_start = int(follow["start"])
                break
        section_text = heading_source_text[int(current["end"]): next_start]
        details = _extract_flow_details(section_text=section_text, major_code=code)
        if details:
            lines.append(f"- {title}：{details[0]}；{details[1]}" if len(details) > 1 else f"- {title}：{details[0]}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines).strip()
