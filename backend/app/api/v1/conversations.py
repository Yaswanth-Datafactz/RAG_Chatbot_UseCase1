"""Conversation CRUD (docs/plan.md Phase 4): create, list, and fetch a
conversation with its messages and citations."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.core.security import require_api_key
from app.db.models import Conversation, Message
from app.db.session import get_db
from app.schemas.conversation import ConversationCreate, ConversationDetail, ConversationOut

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, db: Annotated[Session, Depends(get_db)]) -> Conversation:
    conversation = Conversation(title=body.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: Annotated[Session, Depends(get_db)]) -> list[Conversation]:
    return list(db.execute(select(Conversation).order_by(Conversation.created_at.desc())).scalars().all())


@router.get("/{conversation_id}", response_model=ConversationDetail, responses={404: {"description": "Conversation not found"}})
def get_conversation(conversation_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Conversation:
    conversation = db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages).selectinload(Message.citations))
    ).scalar_one_or_none()
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} not found")
    return conversation
