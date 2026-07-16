"""Pydantic v2 request/response models for conversations, messages, and
citations (Handbook §6.2: Pydantic models on every route)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=500)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    rank: int
    reranker_score: float | None
    section_path: str | None
    snippet: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    refused: bool
    model: str | None
    created_at: datetime
    citations: list[CitationOut] = []


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
