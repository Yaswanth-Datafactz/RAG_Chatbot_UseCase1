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


def _default_generation_adapter(body: ChatMessageRequest) -> GenerationAdapter:
    """A FastAPI dependency wrapping get_generation_adapter(): declaring
    the same `body: ChatMessageRequest` parameter the route itself takes
    lets FastAPI resolve it once and share it, rather than reading the
    request body twice. `body.provider` (the frontend's model picker,
    ChatMessageRequest.provider) overrides GENERATION_PROVIDER for this
    one message when present; get_generation_adapter(None) falls back to
    the configured default exactly as before. Kept as its own
    Depends()-wrapped function (rather than inlined in post_message)
    specifically so tests can override it via
    app.dependency_overrides[_default_generation_adapter] without hitting
    a real generation provider."""
    return get_generation_adapter(body.provider)


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
