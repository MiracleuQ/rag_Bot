import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from app.ingest.models import SourceDocument

MANIFEST_VERSION = 1


def _default_manifest() -> dict:
    return {"version": MANIFEST_VERSION, "docs": {}}


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return _default_manifest()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_manifest()

    if not isinstance(data, dict):
        return _default_manifest()
    if data.get("version") != MANIFEST_VERSION:
        return _default_manifest()
    if not isinstance(data.get("docs"), dict):
        data["docs"] = {}
    return data


def save_manifest(path: Path, docs_state: Dict[str, dict]) -> None:
    payload = {
        "version": MANIFEST_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "docs": docs_state,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_current_doc_index(docs: List[SourceDocument]) -> Dict[str, dict]:
    current: Dict[str, dict] = {}
    for doc in docs:
        relative_path = doc.metadata.get("relative_path", doc.path)
        current[relative_path] = {
            "doc_id": doc.doc_id,
            "content_sha256": doc.metadata.get("content_sha256", ""),
            "source_path": doc.path,
        }
    return current
