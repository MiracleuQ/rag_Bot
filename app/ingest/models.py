from typing import Dict, List

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    doc_id: str
    path: str
    content: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class TextChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class VectorPoint(BaseModel):
    point_id: str
    vector: List[float]
    payload: Dict[str, str]
