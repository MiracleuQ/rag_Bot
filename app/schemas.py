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


class IngestRequest(BaseModel):
    input_dir: Optional[str] = Field(default=None, description="Knowledge base folder path. Defaults to KNOWLEDGE_BASE_DIR.")
    dry_run: bool = Field(default=False, description="Scan and plan only, no write.")
    full_reindex: bool = Field(default=False, description="Ignore incremental diff and rebuild all vectors.")


class IngestResponse(BaseModel):
    kb_dir: str
    document_count: int
    changed_document_count: int
    skipped_document_count: int
    removed_document_count: int
    chunk_count: int
    delete_count: int
    vector_count: int
    duplicate_count: int
    dry_run: bool
    full_reindex: bool
    incremental_enabled: bool
    manifest_path: str
