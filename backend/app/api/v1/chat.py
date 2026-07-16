"""POST /conversations/{id}/messages -- the SSE chat endpoint (docs/plan.md
Decision #10). See docs/phase-4.md for the exact event protocol."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import require_api_key
from app.db.models import Conversation
from app.db.session import get_db
from app.schemas.conversation import ChatMessageRequest
from app.services.chat import stream_chat_response
from app.services.generation import get_generation_adapter
from app.services.generation.base import GenerationAdapter

router = APIRouter(
    prefix="/conversations",
    tags=["chat"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)


def _default_generation_adapter() -> GenerationAdapter:
    """A zero-arg wrapper around get_generation_adapter() for use as a
    FastAPI dependency: get_generation_adapter() itself takes an optional
    `provider` override for tests/callers, and Depends() would otherwise
    expose that as a caller-controlled `provider` query parameter on this
    route, letting any request pick its own generation provider."""
    return get_generation_adapter()


@router.post("/{conversation_id}/messages", responses={404: {"description": "Conversation not found"}})
def post_message(
    conversation_id: uuid.UUID,
    body: ChatMessageRequest,
    db: Annotated[Session, Depends(get_db)],
    adapter: Annotated[GenerationAdapter, Depends(_default_generation_adapter)],
) -> StreamingResponse:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} not found")

    return StreamingResponse(
        stream_chat_response(db, conversation, body.content, adapter),
        media_type="text/event-stream",
    )
