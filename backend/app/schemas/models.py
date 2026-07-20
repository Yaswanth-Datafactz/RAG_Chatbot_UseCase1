"""Pydantic v2 response model for GET /models (Handbook §6.2: Pydantic
models on every route)."""

from __future__ import annotations

from pydantic import BaseModel


class ModelOut(BaseModel):
    id: str
    label: str
    available: bool
    is_default: bool
