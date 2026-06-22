import os
from unittest.mock import patch

from app.config import Settings, get_settings


class TestSettings:
    def test_default_values(self):
        settings = Settings()
        assert settings.app_name == "RAG_Bot"
        assert settings.app_env == "dev"
        assert settings.retriever_mode == "chroma"
        assert settings.rag_top_k == 3
        assert settings.enable_mmr is False
        assert settings.enable_crag is False
        assert settings.enable_hyde is False

    def test_cors_origins_string(self):
        settings = Settings(allow_cors_origins="http://a.com,http://b.com")
        assert settings.allow_cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_star(self):
        settings = Settings(allow_cors_origins="*")
        assert settings.allow_cors_origins == ["*"]

    def test_cors_origins_list(self):
        settings = Settings(allow_cors_origins=["http://a.com"])
        assert settings.allow_cors_origins == ["http://a.com"]

    def test_kb_extensions_string(self):
        settings = Settings(knowledge_base_extensions=".pdf,.docx")
        assert settings.knowledge_base_extensions == [".pdf", ".docx"]

    def test_kb_extensions_without_dot(self):
        settings = Settings(knowledge_base_extensions="pdf,docx")
        assert settings.knowledge_base_extensions == [".pdf", ".docx"]

    def test_kb_extensions_list(self):
        settings = Settings(knowledge_base_extensions=[".pdf", ".txt"])
        assert settings.knowledge_base_extensions == [".pdf", ".txt"]

    def test_chunk_mode_values(self):
        for mode in ["hybrid", "sliding", "parent_child"]:
            settings = Settings(chunk_mode=mode)
            assert settings.chunk_mode == mode

    def test_retriever_mode_values(self):
        for mode in ["chroma", "qdrant"]:
            settings = Settings(retriever_mode=mode)
            assert settings.retriever_mode == mode

    def test_numeric_ranges(self):
        settings = Settings(
            rag_top_k=5,
            ingest_chunk_size=1000,
            ingest_chunk_overlap=200,
            mmr_lambda=0.7,
            crag_correct_threshold=0.6,
        )
        assert settings.rag_top_k == 5
        assert settings.ingest_chunk_size == 1000
        assert settings.ingest_chunk_overlap == 200
        assert settings.mmr_lambda == 0.7
        assert settings.crag_correct_threshold == 0.6


class TestGetSettings:
    def test_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_cached(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
