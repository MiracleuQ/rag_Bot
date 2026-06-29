import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.history.session_service import HistorySessionService
from app.integrations.wechat_adapter import WeChatMessageAdapter
from app.schemas import ChatRequest, ChatResponse, WeChatAdapterRequest, WeChatAdapterResponse
from app.security.rbac import require_permission
from app.services import LangChainRAGService

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT_SEC = 60


def _handle_chat(
    rag_service: LangChainRAGService,
    history_service: HistorySessionService,
    question: str,
    session_id: Optional[str],
    user_id: Optional[str],
    channel: str,
):
    start_time = time.monotonic()
    session_id = history_service.history_session_id(
        provided_session_id=session_id,
        user_id=user_id,
        channel=channel,
        title_seed=question,
    )
    history_context = history_service.load_history_context(session_id)
    result = rag_service.answer(
        question,
        history_messages=history_context,
        session_id=session_id,
    )
    history_service.persist_chat_turn(
        session_id=session_id,
        question=question,
        answer=result.answer,
        used_docs=[doc.model_dump() for doc in result.used_docs],
    )
    elapsed_ms = (time.monotonic() - start_time) * 1000
    logger.info("Chat handled in %.0fms: session=%s docs=%d", elapsed_ms, session_id, len(result.used_docs))
    return result, session_id


def create_chat_router(
    rag_service: LangChainRAGService,
    history_service: HistorySessionService,
) -> APIRouter:
    router = APIRouter()

    @router.post("/chat", response_model=ChatResponse)
    def chat(
        req: ChatRequest,
        ctx=require_permission("chat", "read"),
    ) -> ChatResponse:
        start_time = time.monotonic()
        logger.info("Chat request: session=%s user=%s question=%s role=%s", req.session_id, req.user_id, req.question[:50], ctx.role)
        try:
            result, session_id = _handle_chat(
                rag_service=rag_service,
                history_service=history_service,
                question=req.question,
                session_id=req.session_id,
                user_id=req.user_id,
                channel=req.channel or "api",
            )
            elapsed_ms = (time.monotonic() - start_time) * 1000
            if elapsed_ms > _CHAT_TIMEOUT_SEC * 1000 * 0.8:
                logger.warning("Chat slow response: %.0fms", elapsed_ms)
            logger.info("Chat response: session=%s docs=%d answer_len=%d latency=%.0fms", session_id, len(result.used_docs), len(result.answer), elapsed_ms)
            return ChatResponse(answer=result.answer, used_docs=result.used_docs, session_id=session_id)
        except ValueError as exc:
            logger.error("Chat validation error: %s", exc)
            raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.exception("Chat failed after %.0fms: session=%s", elapsed_ms, req.session_id)
            raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc

    @router.post("/integrations/wechat/adapter", response_model=WeChatAdapterResponse)
    def wechat_adapter(payload: WeChatAdapterRequest) -> WeChatAdapterResponse:
        question = WeChatMessageAdapter.extract_question(payload)
        if not question:
            raise HTTPException(status_code=400, detail="No text question found in payload.")

        try:
            result, session_id = _handle_chat(
                rag_service=rag_service,
                history_service=history_service,
                question=question,
                session_id=WeChatMessageAdapter.resolve_session_id(payload) or None,
                user_id=payload.user_id,
                channel="wechat",
            )
            return WeChatMessageAdapter.build_text_reply(result.answer, session_id=session_id)
        except HTTPException:
            raise
        except ValueError as exc:
            logger.error("WeChat adapter validation error: %s", exc)
            raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
        except Exception as exc:
            logger.exception("WeChat adapter failed: user=%s", payload.user_id)
            raise HTTPException(status_code=500, detail=f"wechat adapter failed: {exc}") from exc

    return router
