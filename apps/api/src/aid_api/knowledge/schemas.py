"""Contratos da Base de conhecimento (ticket #23)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ContentType = Literal[
    "application/pdf",
    "text/markdown",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]
MAX_BYTES = 20 * 1024 * 1024


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    source: Literal["upload", "incident"]
    status: Literal["pending", "indexing", "ready", "failed"]
    content_type: str | None
    size_bytes: int | None
    chunk_count: int
    error: str | None
    created_at: datetime


class GlobalDocument(BaseModel):
    id: str
    slug: str
    title: str
    chunk_count: int


class NewKnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=200, pattern=r"^[^/\\]+$")
    content_type: ContentType
    size_bytes: int = Field(ge=1, le=MAX_BYTES)


class CreatedKnowledgeDocument(BaseModel):
    id: str
    upload_url: str


class KnowledgeQuery(BaseModel):
    """Pergunta no corpo (POST), não na URL: pode citar dado do cliente."""

    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class KnowledgeHit(BaseModel):
    origin: Literal["tenant", "global"]
    document_id: str
    title: str
    heading: str | None
    excerpt: str


class KnowledgeResults(BaseModel):
    items: list[KnowledgeHit]
    # `hybrid` (vetor + texto) ou `text` (provedor de IA fora: só o texto).
    mode: Literal["hybrid", "text"]
