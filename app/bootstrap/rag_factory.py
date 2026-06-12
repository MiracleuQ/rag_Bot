from app.config import Settings
from app.ingest.embedders import create_embedder
from app.llm_client import LLMClient
from app.query_rewrite import LLMQueryRewriter, NoopQueryRewriter, RuleBasedQueryRewriter
from app.retrievers import CRAGRetriever, ChromaRetriever, MMRRetriever, QdrantRetriever
from app.retrievers.base import BaseRetriever
from app.services import LangChainRAGService


def _build_base_retriever(settings: Settings, embedder) -> BaseRetriever:
    if settings.retriever_mode == "chroma":
        return ChromaRetriever(settings=settings, embedder=embedder)
    elif settings.retriever_mode == "qdrant":
        return QdrantRetriever(settings=settings, embedder=embedder)
    else:
        raise ValueError(
            "Unsupported RETRIEVER_MODE. "
            f"expected='chroma|qdrant' actual='{settings.retriever_mode}'"
        )


def _build_retriever_chain(settings: Settings, embedder) -> BaseRetriever:
    retriever: BaseRetriever = _build_base_retriever(settings=settings, embedder=embedder)

    if settings.enable_mmr:
        retriever = MMRRetriever(
            base_retriever=retriever,
            embed_fn=lambda texts: embedder.embed_texts(texts),
            lambda_mult=settings.mmr_lambda,
        )

    if settings.enable_crag:
        llm_client = LLMClient(settings=settings)
        retriever = CRAGRetriever(
            base_retriever=retriever,
            llm_client=llm_client,
            max_retries=settings.crag_max_retries,
            correct_threshold=settings.crag_correct_threshold,
        )

    return retriever


def _build_query_rewriter(settings: Settings, llm_client: LLMClient):
    if not settings.enable_query_rewrite or settings.query_rewrite_mode == "none":
        return NoopQueryRewriter()
    elif settings.query_rewrite_mode == "rule":
        return RuleBasedQueryRewriter(max_chars=settings.query_rewrite_max_chars)
    elif settings.query_rewrite_mode == "llm":
        return LLMQueryRewriter(
            llm_client=llm_client,
            max_chars=settings.query_rewrite_max_chars,
        )
    else:
        return NoopQueryRewriter()


def build_rag_service(settings: Settings) -> LangChainRAGService:
    embedder = create_embedder(settings)
    retriever = _build_retriever_chain(settings=settings, embedder=embedder)
    llm_client = LLMClient(settings=settings)
    query_rewriter = _build_query_rewriter(settings=settings, llm_client=llm_client)

    return LangChainRAGService(
        retriever=retriever,
        llm_client=llm_client,
        top_k=settings.rag_top_k,
        query_rewriter=query_rewriter,
        enable_history_question_rewrite=settings.enable_history_question_rewrite,
        enable_dual_route_retrieval=settings.rag_enable_dual_route_retrieval,
        query_rewrite_cache_enabled=settings.query_rewrite_cache_enabled,
        query_rewrite_cache_ttl_sec=settings.query_rewrite_cache_ttl_sec,
        query_rewrite_cache_max_size=settings.query_rewrite_cache_max_size,
        enable_structured_output=settings.enable_structured_output,
    )
