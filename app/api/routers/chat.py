import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.history.session_service import HistorySessionService
from app.integrations.wechat_adapter import WeChatMessageAdapter
from app.schemas import ChatRequest, ChatResponse, WeChatAdapterRequest, WeChatAdapterResponse
from app.security.rbac import require_permission
from app.services import LangChainRAGService

logger = logging.getLogger(__name__)


def _handle_chat(
    rag_service: LangChainRAGService,
    history_service: HistorySessionService,
    question: str,
    session_id: Optional[str],
    user_id: Optional[str],
    channel: str,
):
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
            logger.info("Chat response: session=%s docs=%d answer_len=%d", session_id, len(result.used_docs), len(result.answer))
            return ChatResponse(answer=result.answer, used_docs=result.used_docs, session_id=session_id)
        except Exception as exc:
            logger.exception("Chat failed: session=%s", req.session_id)
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
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"wechat adapter failed: {exc}") from exc

    return router
