import hmac
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.config import Settings
from app.history import ChatHistoryStore


def _normalize_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class HistorySessionService:
    def __init__(self, settings: Settings, history_store: ChatHistoryStore):
        self._settings = settings
        self._history_store = history_store

    def history_session_id(
        self,
        provided_session_id: Optional[str],
        user_id: Optional[str],
        channel: str,
        title_seed: str,
    ) -> Optional[str]:
        if not self._settings.chat_history_enabled:
            return provided_session_id

        normalized_session_id = _normalize_optional_text(provided_session_id)
        normalized_user_id = _normalize_optional_text(user_id)
        # 会话归属校验：防止用户 A 通过伪造 session_id 读取用户 B 的对话历史。
        # 401 = 已存在的会话缺少身份认证，403 = 身份与会话归属不匹配。
        if self._settings.history_enforce_user_scope and normalized_session_id:
            existing = self._history_store.get_session(normalized_session_id)
            if existing:
                owner_user_id = _normalize_optional_text(existing.get("user_id"))
                if owner_user_id and not normalized_user_id:
                    raise HTTPException(
                        status_code=401,
                        detail="Missing user_id for existing session.",
                    )
                if owner_user_id and normalized_user_id != owner_user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Session does not belong to the provided user_id.",
                    )

        return self._history_store.ensure_session(
            session_id=normalized_session_id,
            user_id=normalized_user_id,
            channel=channel,
            title_seed=title_seed,
        )

    def persist_chat_turn(
        self,
        session_id: Optional[str],
        question: str,
        answer: str,
        used_docs: List[dict],
    ) -> None:
        if not self._settings.chat_history_enabled or not session_id:
            return
        self._history_store.append_message(session_id=session_id, role="user", content=question)
        self._history_store.append_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            used_docs=used_docs,
        )

    def load_history_context(self, session_id: Optional[str]) -> List[dict]:
        if not self._settings.chat_history_enabled or not self._settings.enable_history_context:
            return []
        if not session_id:
            return []
        if self._settings.history_context_max_messages <= 0:
            return []

        rows = self._history_store.list_recent_messages(
            session_id=session_id,
            limit=self._settings.history_context_max_messages,
        )
        return [
            {"role": str(row.get("role", "")), "content": str(row.get("content", ""))}
            for row in rows
            if row.get("role") in {"user", "assistant"} and str(row.get("content", "")).strip()
        ]

    def assert_history_enabled(self) -> None:
        if not self._settings.chat_history_enabled:
            raise HTTPException(status_code=400, detail="Chat history is disabled.")

    def resolve_history_scope_user(
        self,
        query_user_id: Optional[str],
        x_user_id: Optional[str],
        x_history_admin_token: Optional[str],
    ) -> Optional[str]:
        requested_user_id = _normalize_optional_text(query_user_id)
        caller_user_id = _normalize_optional_text(x_user_id)
        admin_token = _normalize_optional_text(x_history_admin_token)
        # Admin 可跨用户查询，绕过归属校验；普通用户只能查自己的会话。
        is_admin = bool(self._settings.history_admin_token) and bool(admin_token) and hmac.compare_digest(
            admin_token, self._settings.history_admin_token
        )

        if not self._settings.history_enforce_user_scope or is_admin:
            return requested_user_id

        if not caller_user_id:
            raise HTTPException(status_code=401, detail="Missing X-User-ID header.")

        if requested_user_id and requested_user_id != caller_user_id:
            raise HTTPException(
                status_code=403,
                detail="X-User-ID does not match requested user scope.",
            )
        return caller_user_id

    def assert_session_access(
        self,
        session_id: str,
        scope_user_id: Optional[str],
        x_user_id: Optional[str],
        x_history_admin_token: Optional[str],
    ) -> None:
        requested_session_id = session_id.strip()
        if not requested_session_id:
            raise HTTPException(status_code=400, detail="session_id is required.")

        caller_user_id = _normalize_optional_text(x_user_id)
        admin_token = _normalize_optional_text(x_history_admin_token)
        is_admin = bool(self._settings.history_admin_token) and bool(admin_token) and hmac.compare_digest(
            admin_token, self._settings.history_admin_token
        )
        if not self._settings.history_enforce_user_scope or is_admin:
            return

        if not caller_user_id:
            raise HTTPException(status_code=401, detail="Missing X-User-ID header.")

        session = self._history_store.get_session(requested_session_id)
        # 会话不存在时不拒绝访问——由调用方决定是否允许对空会话的操作。
        if not session:
            return

        owner_user_id = _normalize_optional_text(session.get("user_id"))
        # scope_user_id 优先（来自 query param），fallback 到 X-User-ID header。
        effective_scope_user = _normalize_optional_text(scope_user_id) or caller_user_id
        if owner_user_id and owner_user_id != effective_scope_user:
            raise HTTPException(status_code=403, detail="Forbidden session access.")

    def list_sessions(
        self,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self._history_store.list_sessions(
            user_id=user_id,
            channel=channel,
            limit=limit,
        )

    def list_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return self._history_store.list_messages(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
