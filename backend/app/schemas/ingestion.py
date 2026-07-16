"""Pydantic v2 response model for ingestion runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    embedding_model: str
    doc_count: int
    chunk_count: int
    is_current: bool
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
