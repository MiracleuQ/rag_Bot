import time

from fastapi import APIRouter

from app.config import Settings

_START_TIME = time.monotonic()


def create_system_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        uptime_sec = int(time.monotonic() - _START_TIME)
        return {
            "status": "ok",
            "version": "0.1.0",
            "env": settings.app_env,
            "uptime_sec": uptime_sec,
            "retriever_mode": settings.retriever_mode,
            "chunk_mode": settings.chunk_mode,
            "query_rewrite_mode": settings.query_rewrite_mode if settings.enable_query_rewrite else "none",
            "query_rewrite_cache_enabled": settings.query_rewrite_cache_enabled,
            "dual_route_retrieval_enabled": settings.rag_enable_dual_route_retrieval,
            "mmr_enabled": settings.enable_mmr,
            "crag_enabled": settings.enable_crag,
            "cross_encoder_enabled": settings.enable_cross_encoder_reranker,
            "hyde_enabled": settings.enable_hyde,
            "structured_output_enabled": settings.enable_structured_output,
            "chat_history_enabled": settings.chat_history_enabled,
            "history_context_enabled": settings.enable_history_context and settings.chat_history_enabled,
            "history_question_rewrite_enabled": settings.enable_history_question_rewrite,
            "vector_store_mode": settings.vector_store_mode,
            "rbac_enabled": settings.rbac_enabled,
            "tenant_isolation_enabled": settings.tenant_isolation_enabled,
        }

    return router
