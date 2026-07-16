"""Pydantic v2 request/response models for documents and chunks."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_filename: str
    title: str
    doc_type: str
    byte_size: int
    created_at: datetime
    current_chunk_count: int


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    section_path: str | None
    content: str
    token_count: int
    page_no: int | None
