from fastapi import APIRouter, HTTPException

from app.history.session_service import HistorySessionService
from app.integrations.wechat_adapter import WeChatMessageAdapter
from app.schemas import ChatRequest, ChatResponse, WeChatAdapterRequest, WeChatAdapterResponse
from app.services import LangChainRAGService


def create_chat_router(
    rag_service: LangChainRAGService,
    history_service: HistorySessionService,
) -> APIRouter:
    router = APIRouter()

    @router.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        session_id = history_service.history_session_id(
            provided_session_id=req.session_id,
            user_id=req.user_id,
            channel=req.channel or "api",
            title_seed=req.question,
        )
        history_context = history_service.load_history_context(session_id)
        try:
            result = rag_service.answer(
                req.question,
                history_messages=history_context,
                session_id=session_id,
            )
            history_service.persist_chat_turn(
                session_id=session_id,
                question=req.question,
                answer=result.answer,
                used_docs=[doc.model_dump() for doc in result.used_docs],
            )
            return ChatResponse(answer=result.answer, used_docs=result.used_docs, session_id=session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc

    @router.post("/integrations/wechat/adapter", response_model=WeChatAdapterResponse)
    def wechat_adapter(payload: WeChatAdapterRequest) -> WeChatAdapterResponse:
        question = WeChatMessageAdapter.extract_question(payload)
        if not question:
            raise HTTPException(status_code=400, detail="No text question found in payload.")

        session_id = history_service.history_session_id(
            provided_session_id=WeChatMessageAdapter.resolve_session_id(payload) or None,
            user_id=payload.user_id,
            channel="wechat",
            title_seed=question,
        )
        history_context = history_service.load_history_context(session_id)
        try:
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
            return WeChatMessageAdapter.build_text_reply(result.answer, session_id=session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"wechat adapter failed: {exc}") from exc

    return router
