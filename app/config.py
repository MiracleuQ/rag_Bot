from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "RAG Bot"
    app_env: str = "dev"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_sec: int = 30

    rag_top_k: int = 3
    rag_candidate_k: int = 8
    rag_max_retrieval_distance: float = 1.25
    rag_min_chunk_chars: int = 20
    rag_enable_dual_route_retrieval: bool = True
    retriever_mode: str = "chroma"  # chroma | qdrant
    enable_query_rewrite: bool = False
    query_rewrite_mode: str = "none"  # none | rule | llm
    query_rewrite_max_chars: int = 256
    query_rewrite_cache_enabled: bool = True
    query_rewrite_cache_ttl_sec: int = 900
    query_rewrite_cache_max_size: int = 512
    chat_history_enabled: bool = True
    chat_history_db_path: str = "data/chat_history/chat_history.db"
    enable_history_context: bool = True
    history_context_max_messages: int = 8
    enable_history_question_rewrite: bool = True
    history_enforce_user_scope: bool = True
    history_admin_token: str = ""

    # Batch ingestion / vectorization settings
    knowledge_base_dir: str = "data/knowledge_base"
    knowledge_base_extensions: List[str] = Field(
        default_factory=lambda: [".txt", ".md", ".pdf", ".doc", ".docx", ".xlsx", ".csv", ".json"]
    )
    pdf_ocr_fallback_enabled: bool = True
    pdf_text_min_chars: int = 30
    pdf_ocr_engine: str = "tesseract"  # tesseract
    pdf_ocr_lang: str = "chi_sim+eng"
    pdf_ocr_dpi: int = 200
    pdf_ocr_max_pages: int = 0
    pdf_ocr_tesseract_cmd: str = ""
    chunk_mode: str = "hybrid"  # hybrid | sliding | parent_child
    ingest_chunk_size: int = 800
    ingest_chunk_overlap: int = 120
    ingest_parent_chunk_size: int = 2000
    ingest_manifest_path: str = "data/vector_store/ingest_manifest.json"
    ingest_enable_incremental: bool = True

    enable_mmr: bool = False
    mmr_lambda: float = 0.5

    enable_crag: bool = False
    crag_max_retries: int = 1
    crag_correct_threshold: float = 0.5

    enable_cross_encoder_reranker: bool = False
    cross_encoder_model: str = "BAAI/bge-reranker-v2-m3"
    cross_encoder_top_n: int = 5

    enable_hyde: bool = False

    embedding_dedup_threshold: float = 0.95

    enable_structured_output: bool = True

    embedding_provider: str = "openai"  # openai
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_timeout_sec: int = 30
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 32

    vector_store_mode: str = "chroma"  # chroma | qdrant
    vector_store_collection: str = "rag_kb_default"
    chroma_persist_dir: str = "data/vector_store/chroma"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_timeout_sec: int = 30

    allow_cors_origins: List[str] = Field(default_factory=list)

    # RBAC (Role-Based Access Control)
    rbac_enabled: bool = False
    rbac_default_role: str = "viewer"
    rbac_admin_token: str = ""

    # Tenant isolation
    tenant_isolation_enabled: bool = False
    tenant_id: str = "default"

    # Reserved for enterprise WeChat adapter
    wechat_token: str = ""
    wechat_aes_key: str = ""
    wechat_corp_id: str = ""

    @field_validator("allow_cors_origins", mode="before")
    @classmethod
    def parse_allow_cors_origins(cls, value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            if value.strip() == "*":
                return ["*"]
            return [item.strip() for item in value.split(",") if item.strip()]
        return ["*"]

    @field_validator("knowledge_base_extensions", mode="before")
    @classmethod
    def parse_kb_extensions(cls, value):
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",") if item.strip()]
        else:
            return [".txt", ".md", ".pdf", ".doc", ".docx", ".xlsx", ".csv", ".json"]

        normalized = []
        for ext in raw_items:
            item = ext.lower()
            if not item.startswith("."):
                item = f".{item}"
            normalized.append(item)
        return normalized or [".txt", ".md", ".pdf", ".doc", ".docx", ".xlsx", ".csv", ".json"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
