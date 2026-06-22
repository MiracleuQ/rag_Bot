import json
import tempfile
from pathlib import Path

from app.ingest.manifest import load_manifest, save_manifest, build_current_doc_index, MANIFEST_VERSION
from app.ingest.models import SourceDocument


class TestLoadManifest:
    def test_nonexistent_file(self):
        result = load_manifest(Path("/nonexistent/manifest.json"))
        assert result["version"] == MANIFEST_VERSION
        assert result["docs"] == {}

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            f.flush()
            result = load_manifest(Path(f.name))
        assert result["version"] == MANIFEST_VERSION
        assert result["docs"] == {}

    def test_wrong_version(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"version": 999, "docs": {}}, f)
            f.flush()
            result = load_manifest(Path(f.name))
        assert result["version"] == MANIFEST_VERSION

    def test_valid_manifest(self):
        data = {"version": MANIFEST_VERSION, "docs": {"a.pdf": {"doc_id": "d1"}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = load_manifest(Path(f.name))
        assert result["docs"]["a.pdf"]["doc_id"] == "d1"


class TestSaveManifest:
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            save_manifest(path, docs_state={"a.pdf": {"doc_id": "d1"}})
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["version"] == MANIFEST_VERSION
            assert data["docs"]["a.pdf"]["doc_id"] == "d1"
            assert "updated_at" in data

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "manifest.json"
            save_manifest(path, docs_state={})
            assert path.exists()

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            save_manifest(path, docs_state={"a": {"doc_id": "1"}})
            save_manifest(path, docs_state={"b": {"doc_id": "2"}})
            data = json.loads(path.read_text())
            assert "b" in data["docs"]
            assert "a" not in data["docs"]


class TestBuildCurrentDocIndex:
    def test_empty_docs(self):
        result = build_current_doc_index([])
        assert result == {}

    def test_single_doc(self):
        doc = SourceDocument(
            doc_id="d1",
            path="/path/to/file.pdf",
            content="hello",
            metadata={"relative_path": "file.pdf", "content_sha256": "abc"},
        )
        result = build_current_doc_index([doc])
        assert "file.pdf" in result
        assert result["file.pdf"]["doc_id"] == "d1"
        assert result["file.pdf"]["content_sha256"] == "abc"

    def test_multiple_docs(self):
        docs = [
            SourceDocument(doc_id=f"d{i}", path=f"/path/{i}.pdf", content=f"content {i}")
            for i in range(3)
        ]
        result = build_current_doc_index(docs)
        assert len(result) == 3
