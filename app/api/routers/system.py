from fastapi import APIRouter

from app.config import Settings


def create_system_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "env": settings.app_env,
            "retriever_mode": settings.retriever_mode,
            "chunk_mode": settings.chunk_mode,
            "query_rewrite_mode": settings.query_rewrite_mode if settings.enable_query_rewrite else "none",
            "query_rewrite_cache_enabled": settings.query_rewrite_cache_enabled,
            "dual_route_retrieval_enabled": settings.rag_enable_dual_route_retrieval,
            "mmr_enabled": settings.enable_mmr,
            "crag_enabled": settings.enable_crag,
            "structured_output_enabled": settings.enable_structured_output,
            "chat_history_enabled": settings.chat_history_enabled,
            "history_context_enabled": settings.enable_history_context and settings.chat_history_enabled,
            "history_question_rewrite_enabled": settings.enable_history_question_rewrite,
            "vector_store_mode": settings.vector_store_mode,
        }

    return router
