from typing import List, Optional

from pydantic import BaseModel, Field


class Document(BaseModel):
    doc_id: str = Field(description="Document identifier")
    content: str = Field(description="Chunk content")
    source: Optional[str] = Field(default=None, description="Source filename or URI")
    score: Optional[float] = Field(default=None, description="Retriever relevance score")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, description="User query")
    session_id: Optional[str] = Field(default=None, description="Session id for history continuity")
    user_id: Optional[str] = Field(default=None, description="User id for conversation owner")
    channel: str = Field(default="api", description="Conversation channel, e.g. api/wechat")


class ChatResponse(BaseModel):
    answer: str
    used_docs: List[Document] = Field(default_factory=list)
    session_id: Optional[str] = None


class WeChatAdapterRequest(BaseModel):
    # Generic payload for future enterprise WeChat adapter
    content: Optional[str] = None
    msgtype: Optional[str] = None
    text: Optional[dict] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    chat_id: Optional[str] = None


class WeChatAdapterResponse(BaseModel):
    msgtype: str = "text"
    text: dict
    session_id: Optional[str] = None


class SessionRecord(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    channel: str
    title: Optional[str] = None
    created_at: str
    updated_at: str


class MessageRecord(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    used_docs: List[Document] = Field(default_factory=list)
    created_at: str
