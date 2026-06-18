import re
from pathlib import Path
from typing import List

from app.ingest.models import SourceDocument, TextChunk

HEADING_PATTERNS = (
    r"^#{1,6}\s+",  # Markdown heading
    r"^第[一二三四五六七八九十百千0-9]+[章节条部分]\s*",  # 第X章/节/条
    r"^[一二三四五六七八九十]+[、.．]\s*",  # 一、 二、 ...
    r"^\d+(\.\d+)*[、.．)\)]\s*",  # 1. / 1.1 / 1)
)
# 标题检测决定分块的边界：遇到标题即认为进入新章节。
# 这样每个 chunk 不会跨章节，保证检索返回的内容在语义上自成一体。


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_doc_title(doc: SourceDocument) -> str:
    filename = doc.metadata.get("filename", "")
    if not filename:
        filename = Path(doc.path).stem
    title = re.sub(r"^WI-[A-Z]{2}-\d+\s*", "", filename)
    title = re.sub(r"\.(pdf|docx?|xlsx?|txt|md)$", "", title, flags=re.IGNORECASE)
    return title.strip() or filename


def _extract_section_heading(chunk_text: str) -> str:
    lines = chunk_text.strip().split("\n")
    for line in lines[:3]:
        line = line.strip()
        if _is_heading(line):
            cleaned = re.sub(r"\s+", " ", line).strip(" ：:;；。 \t\r\n")
            if len(cleaned) > 60:
                cleaned = cleaned[:60]
            return cleaned
    return ""


def _is_heading(line: str) -> bool:
    content = line.strip()
    if not content:
        return False
    return any(re.match(pattern, content) for pattern in HEADING_PATTERNS)


def _tail_overlap(text: str, overlap: int) -> str:
    if overlap <= 0 or not text:
        return ""
    return text[-overlap:]


def _sliding_window_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    chunks: List[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def _split_sections(text: str) -> List[str]:
    lines = text.split("\n")
    sections: List[str] = []
    current: List[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current and current[-1] != "":
                current.append("")
            continue

        if _is_heading(line) and current:
            section_text = "\n".join(current).strip()
            if section_text:
                sections.append(section_text)
            current = [line]
        else:
            current.append(line)

    if current:
        section_text = "\n".join(current).strip()
        if section_text:
            sections.append(section_text)

    return sections or [text]


def _split_sentences(text: str) -> List[str]:
    normalized = re.sub(r"\n+", " ", text).strip()
    if not normalized:
        return []

    # 按中英文常见句末标点切分，保留标点便于语义完整。
    parts = re.split(r"(?<=[。！？!?；;])", normalized)
    sentences = [part.strip() for part in parts if part and part.strip()]
    return sentences or [normalized]


def _split_to_units(section_text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", section_text) if p.strip()]
    if not paragraphs:
        paragraphs = [section_text.strip()]

    units: List[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            units.append(para)
            continue

        sentences = _split_sentences(para)
        if len(sentences) <= 1:
            units.extend(_sliding_window_split(para, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
        else:
            units.extend(sentences)
    return units


def _pack_units(units: List[str], chunk_size: int, chunk_overlap: int) -> List[str]:
    chunks: List[str] = []
    current = ""

    for unit in units:
        text = unit.strip()
        if not text:
            continue

        candidate = text if not current else f"{current}\n{text}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(text) > chunk_size:
            # 当前 unit 超过 chunk_size，先对超长文本做滑动窗口切分，
            # 再把最后一小片留作 current，与后续短 unit 拼接。
            long_chunks = _sliding_window_split(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            if long_chunks:
                chunks.extend(long_chunks[:-1])
                current = long_chunks[-1]
            else:
                current = ""
            continue

        # 从上一 chunk 尾部取 overlap 长度的文本，与新 unit 拼接，
        # 保证相邻 chunk 之间有重叠，提升检索时的上下文连续性。
        overlap_text = _tail_overlap(current, chunk_overlap)
        current = f"{overlap_text}\n{text}".strip() if overlap_text else text
        if len(current) > chunk_size:
            current = text

    if current:
        chunks.append(current)
    return chunks


def _hybrid_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    # 混合分块流水线：按标题切章节 → 按段落/句子拆为最小单元 → 贪心打包不超过 chunk_size。
    # 相比纯滑动窗口，能尽量保留段落和句子的语义完整性。
    sections = _split_sections(text)
    chunks: List[str] = []

    for section in sections:
        units = _split_to_units(
            section_text=section,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks.extend(_pack_units(units, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return [chunk for chunk in chunks if chunk.strip()]


def _parent_child_split(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    parent_chunk_size: int,
) -> List[dict]:
    sections = _split_sections(text)
    result: List[dict] = []

    for section in sections:
        section_text = section.strip()
        if not section_text:
            continue

        if len(section_text) <= parent_chunk_size:
            parent_texts = [section_text]
        else:
            parent_texts = _sliding_window_split(
                section_text, chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap,
            )

        for parent_text in parent_texts:
            child_units = _split_to_units(
                section_text=parent_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            child_texts = _pack_units(
                child_units, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            )
            child_texts = [c for c in child_texts if c.strip()]
            if not child_texts:
                child_texts = [parent_text[:chunk_size]]

            result.append({"parent": parent_text, "children": child_texts})

    return result


def split_document(
    doc: SourceDocument,
    chunk_size: int,
    chunk_overlap: int,
    mode: str = "hybrid",
    parent_chunk_size: int = 2000,
) -> List[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    text = _normalize_text(doc.content)
    if not text:
        return []

    doc_title = _extract_doc_title(doc)

    if mode == "parent_child":
        return _split_parent_child(
            doc=doc,
            text=text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            parent_chunk_size=parent_chunk_size,
            doc_title=doc_title,
        )

    if mode == "sliding":
        chunk_texts = _sliding_window_split(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    else:
        chunk_texts = _hybrid_split(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks: List[TextChunk] = []
    search_from = 0
    for idx, chunk_text in enumerate(chunk_texts, start=1):
        start = text.find(chunk_text, max(0, search_from - chunk_overlap - 8))
        if start < 0:
            start = max(0, search_from)
        end = start + len(chunk_text)
        search_from = end

        section_heading = _extract_section_heading(chunk_text)
        prefix = f"[文档: {doc_title}]"
        if section_heading:
            prefix += f"\n[章节: {section_heading}]"
        enriched_text = f"{prefix}\n{chunk_text}"

        chunks.append(
            TextChunk(
                chunk_id=f"{doc.doc_id}-chunk-{idx}",
                doc_id=doc.doc_id,
                text=enriched_text,
                metadata={
                    "source_path": doc.path,
                    "relative_path": doc.metadata.get("relative_path", doc.path),
                    "chunk_index": str(idx),
                    "start": str(start),
                    "end": str(end),
                    "chunk_mode": mode,
                    "doc_title": doc_title,
                    "section_heading": section_heading,
                },
            )
        )
    return chunks


def _split_parent_child(
    doc: SourceDocument,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    parent_chunk_size: int,
    doc_title: str = "",
) -> List[TextChunk]:
    pc_groups = _parent_child_split(
        text=text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        parent_chunk_size=parent_chunk_size,
    )

    chunks: List[TextChunk] = []
    parent_idx = 0
    child_global_idx = 0

    for group in pc_groups:
        parent_idx += 1
        parent_id = f"{doc.doc_id}-parent-{parent_idx}"
        parent_text = group["parent"]
        section_heading = _extract_section_heading(parent_text)

        prefix = f"[文档: {doc_title}]"
        if section_heading:
            prefix += f"\n[章节: {section_heading}]"
        enriched_parent = f"{prefix}\n{parent_text}"

        chunks.append(
            TextChunk(
                chunk_id=parent_id,
                doc_id=doc.doc_id,
                text=enriched_parent,
                metadata={
                    "source_path": doc.path,
                    "relative_path": doc.metadata.get("relative_path", doc.path),
                    "chunk_index": str(parent_idx),
                    "chunk_mode": "parent_child",
                    "chunk_level": "parent",
                    "doc_title": doc_title,
                    "section_heading": section_heading,
                },
            )
        )

        for child_text in group["children"]:
            child_global_idx += 1
            child_id = f"{doc.doc_id}-child-{child_global_idx}"
            enriched_child = f"{prefix}\n{child_text}" if not section_heading else f"{prefix}\n{child_text}"
            chunks.append(
                TextChunk(
                    chunk_id=child_id,
                    doc_id=doc.doc_id,
                    text=enriched_child,
                    metadata={
                        "source_path": doc.path,
                        "relative_path": doc.metadata.get("relative_path", doc.path),
                        "chunk_index": str(child_global_idx),
                        "chunk_mode": "parent_child",
                        "chunk_level": "child",
                        "parent_chunk_id": parent_id,
                        "doc_title": doc_title,
                        "section_heading": section_heading,
                    },
                )
            )

    return chunks
