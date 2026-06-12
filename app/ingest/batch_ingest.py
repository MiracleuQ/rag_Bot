import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from app.config import get_settings
from app.ingest.chunker import split_document
from app.ingest.document_loader import PDFParseOptions, load_documents
from app.ingest.embedders import create_embedder
from app.ingest.manifest import build_current_doc_index, load_manifest, save_manifest
from app.ingest.models import TextChunk, VectorPoint
from app.ingest.vector_store import create_vector_store


def _build_pdf_options() -> PDFParseOptions:
    settings = get_settings()
    return PDFParseOptions(
        ocr_fallback_enabled=settings.pdf_ocr_fallback_enabled,
        text_min_chars=settings.pdf_text_min_chars,
        ocr_engine=settings.pdf_ocr_engine,
        ocr_lang=settings.pdf_ocr_lang,
        ocr_dpi=settings.pdf_ocr_dpi,
        ocr_max_pages=settings.pdf_ocr_max_pages,
        ocr_tesseract_cmd=settings.pdf_ocr_tesseract_cmd,
    )


def _batch(items: List[TextChunk], batch_size: int) -> List[List[TextChunk]]:
    size = max(1, batch_size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_stale_point_ids(paths: List[str], prev_docs_state: Dict[str, dict]) -> List[str]:
    ids: List[str] = []
    for path in paths:
        entry = prev_docs_state.get(path) or {}
        point_ids = entry.get("point_ids") or []
        for point_id in point_ids:
            if isinstance(point_id, str) and point_id:
                ids.append(point_id)
    # Keep order while deduping.
    return list(dict.fromkeys(ids))


def run_ingestion(
    input_dir: str | None = None,
    dry_run: bool = False,
    full_reindex: bool = False,
) -> dict:
    settings = get_settings()
    kb_dir = Path(input_dir or settings.knowledge_base_dir)
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    manifest_path = Path(settings.ingest_manifest_path)
    prev_manifest = load_manifest(manifest_path)
    prev_docs_state: Dict[str, dict] = prev_manifest.get("docs", {})

    docs = load_documents(
        kb_dir,
        settings.knowledge_base_extensions,
        pdf_options=_build_pdf_options(),
    )
    current_doc_index = build_current_doc_index(docs)
    docs_by_rel_path = {doc.metadata.get("relative_path", doc.path): doc for doc in docs}

    current_paths = set(current_doc_index.keys())
    prev_paths = set(prev_docs_state.keys())

    removed_paths: List[str] = []
    changed_paths: List[str] = []
    skipped_paths: List[str] = []
    stale_paths: List[str] = []

    if full_reindex:
        changed_paths = sorted(current_paths)
        removed_paths = sorted(prev_paths - current_paths)
        stale_paths = sorted(prev_paths)
    elif settings.ingest_enable_incremental:
        removed_paths = sorted(prev_paths - current_paths)
        for path in sorted(current_paths):
            current_state = current_doc_index[path]
            prev_state = prev_docs_state.get(path)
            if not prev_state:
                changed_paths.append(path)
                continue
            if (
                prev_state.get("doc_id") != current_state.get("doc_id")
                or prev_state.get("content_sha256") != current_state.get("content_sha256")
            ):
                changed_paths.append(path)
            else:
                skipped_paths.append(path)
        stale_paths = sorted(set(removed_paths + changed_paths))
    else:
        changed_paths = sorted(current_paths)

    stale_point_ids = _collect_stale_point_ids(stale_paths, prev_docs_state)

    chunks_to_upsert: List[TextChunk] = []
    point_ids_by_path: Dict[str, List[str]] = {}
    for path in changed_paths:
        doc = docs_by_rel_path[path]
        doc_chunks = split_document(
            doc=doc,
            chunk_size=settings.ingest_chunk_size,
            chunk_overlap=settings.ingest_chunk_overlap,
            mode=settings.chunk_mode,
            parent_chunk_size=settings.ingest_parent_chunk_size,
        )
        chunks_to_upsert.extend(doc_chunks)
        point_ids_by_path[path] = [chunk.chunk_id for chunk in doc_chunks]

    new_point_ids = {
        point_id
        for point_ids in point_ids_by_path.values()
        for point_id in point_ids
        if point_id
    }
    # 从待清理列表中排除本次新生成的 point_id：
    # 同一文档的 chunk 可能在重新分块后保持相同 ID（如 chunk-1, chunk-2），
    # 此时应走 upsert 更新而非删除再插入。
    stale_point_ids_to_delete = [point_id for point_id in stale_point_ids if point_id not in new_point_ids]

    result = {
        "kb_dir": str(kb_dir),
        "document_count": len(docs),
        "changed_document_count": len(changed_paths),
        "skipped_document_count": len(skipped_paths),
        "removed_document_count": len(removed_paths),
        "chunk_count": len(chunks_to_upsert),
        "delete_count": len(stale_point_ids_to_delete),
        "vector_count": 0,
        "dry_run": dry_run,
        "full_reindex": full_reindex,
        "incremental_enabled": settings.ingest_enable_incremental and not full_reindex,
        "manifest_path": str(manifest_path),
    }
    if dry_run:
        return result

    store = create_vector_store(settings)
    if chunks_to_upsert:
        embedder = create_embedder(settings)
        total_vectors = 0
        for chunk_batch in _batch(chunks_to_upsert, settings.embedding_batch_size):
            vectors = embedder.embed_texts([item.text for item in chunk_batch])
            if len(vectors) != len(chunk_batch):
                # Embedding API 可能因超时/限流等原因静默丢失部分结果。
                # 此时必须中止入库，否则向量与文本错位导致检索返回错误内容。
                raise RuntimeError(
                    "Embedding result size mismatch. "
                    f"expected={len(chunk_batch)} actual={len(vectors)} "
                    "The ingestion run is aborted to avoid silent vector loss."
                )
            points = [
                VectorPoint(
                    point_id=item.chunk_id,
                    vector=vector,
                    payload={
                        "doc_id": item.doc_id,
                        "text": item.text,
                        "source_path": item.metadata.get("source_path", ""),
                        "chunk_index": item.metadata.get("chunk_index", ""),
                        "relative_path": item.metadata.get("relative_path", ""),
                        "chunk_mode": item.metadata.get("chunk_mode", settings.chunk_mode),
                    },
                )
                for item, vector in zip(chunk_batch, vectors)
            ]
            store.upsert(points)
            total_vectors += len(points)
        result["vector_count"] = total_vectors

    if stale_point_ids_to_delete:
        store.delete_points(stale_point_ids_to_delete)

    new_docs_state: Dict[str, dict] = {}
    now = _now_utc()

    for path in skipped_paths:
        prev_state = prev_docs_state.get(path)
        if prev_state:
            new_docs_state[path] = prev_state

    for path in changed_paths:
        doc = docs_by_rel_path[path]
        current_state = current_doc_index[path]
        new_docs_state[path] = {
            "doc_id": current_state["doc_id"],
            "source_path": current_state["source_path"],
            "content_sha256": current_state["content_sha256"],
            "chunk_count": len(point_ids_by_path.get(path, [])),
            "point_ids": point_ids_by_path.get(path, []),
            "updated_at": now,
        }

    if not settings.ingest_enable_incremental and not full_reindex:
        # Non-incremental mode still records current state for future switch-over.
        for path in sorted(current_paths):
            if path in new_docs_state:
                continue
            doc = docs_by_rel_path[path]
            current_state = current_doc_index[path]
            new_docs_state[path] = {
                "doc_id": current_state["doc_id"],
                "source_path": current_state["source_path"],
                "content_sha256": current_state["content_sha256"],
                "chunk_count": 0,
                "point_ids": [],
                "updated_at": now,
            }

    save_manifest(manifest_path, docs_state=new_docs_state)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch vectorize docs from a folder.")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Knowledge base folder path. Defaults to KNOWLEDGE_BASE_DIR in .env.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan and plan only, no write.")
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Ignore incremental diff and rebuild vectors for all current documents.",
    )
    args = parser.parse_args()

    summary = run_ingestion(
        input_dir=args.input_dir,
        dry_run=args.dry_run,
        full_reindex=args.full_reindex,
    )
    print("Batch ingestion summary:")
    for key, value in summary.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
