from app.schemas import WeChatAdapterRequest, WeChatAdapterResponse


class WeChatMessageAdapter:
    """Enterprise WeChat adapter placeholder."""

    @staticmethod
    def extract_question(payload: WeChatAdapterRequest) -> str:
        if payload.content:
            return payload.content.strip()

        if payload.text and isinstance(payload.text, dict):
            content = payload.text.get("content", "")
            if isinstance(content, str):
                return content.strip()

        return ""

    @staticmethod
    def resolve_session_id(payload: WeChatAdapterRequest) -> str:
        if payload.session_id and payload.session_id.strip():
            return payload.session_id.strip()
        if payload.user_id and payload.chat_id:
            return f"wechat:{payload.user_id.strip()}:{payload.chat_id.strip()}"
        if payload.user_id:
            return f"wechat:{payload.user_id.strip()}"
        return ""

    @staticmethod
    def build_text_reply(answer: str, session_id: str | None = None) -> WeChatAdapterResponse:
        return WeChatAdapterResponse(msgtype="text", text={"content": answer}, session_id=session_id)
