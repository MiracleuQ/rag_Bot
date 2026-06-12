from typing import List, Optional

from fastapi import APIRouter, Header, Query

from app.history.session_service import HistorySessionService
from app.schemas import MessageRecord, SessionRecord


def create_history_router(history_service: HistorySessionService) -> APIRouter:
    router = APIRouter()

    @router.get("/history/sessions", response_model=List[SessionRecord])
    def history_sessions(
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = Query(default=20, ge=1, le=200),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
        x_history_admin_token: Optional[str] = Header(default=None, alias="X-History-Admin-Token"),
    ) -> List[SessionRecord]:
        history_service.assert_history_enabled()
        scope_user_id = history_service.resolve_history_scope_user(
            query_user_id=user_id,
            x_user_id=x_user_id,
            x_history_admin_token=x_history_admin_token,
        )
        rows = history_service.list_sessions(user_id=scope_user_id, channel=channel, limit=limit)
        return [SessionRecord(**row) for row in rows]

    @router.get("/history/sessions/{session_id}/messages", response_model=List[MessageRecord])
    def history_messages(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
        x_history_admin_token: Optional[str] = Header(default=None, alias="X-History-Admin-Token"),
    ) -> List[MessageRecord]:
        history_service.assert_history_enabled()
        scope_user_id = history_service.resolve_history_scope_user(
            query_user_id=None,
            x_user_id=x_user_id,
            x_history_admin_token=x_history_admin_token,
        )
        history_service.assert_session_access(
            session_id=session_id,
            scope_user_id=scope_user_id,
            x_user_id=x_user_id,
            x_history_admin_token=x_history_admin_token,
        )
        rows = history_service.list_messages(session_id=session_id, limit=limit, offset=offset)
        return [MessageRecord(**row) for row in rows]

    return router
