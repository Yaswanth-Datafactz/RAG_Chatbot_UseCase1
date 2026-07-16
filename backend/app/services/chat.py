"""Chat orchestration (docs/plan.md Decision #10): load history -> rewrite
-> retrieve -> refusal gate -> stream the answer (or the fixed refusal
message) -> persist.

Structured as an async generator that yields raw SSE wire frames
(`event: ...\\ndata: ...\\n\\n`) directly: this module owns the pipeline
order and the persistence side effects (Decision #10: citations before
tokens), and api/v1/chat.py is a thin router that only wraps this
generator in a StreamingResponse. See docs/phase-4.md for the exact event
protocol this produces.

retrieval.retrieve() and rewrite.rewrite_query()'s `generate_fn` are
synchronous, blocking calls (Phase 2/3's embedding and search clients use
the sync Azure SDKs) -- both are dispatched via Starlette's
run_in_threadpool so they never block the event loop other requests share
(Handbook §6.2: async I/O for all LLM/network calls). The generation
adapter itself (this phase's own code) uses the async Claude/Azure OpenAI
clients directly, so its calls are awaited in place. Plain local Postgres
reads/writes (loading history, persisting messages/citations) are done
directly on the request's own task, consistent with how every other route
in this codebase already uses the synchronous SQLAlchemy Session.

Any of the three pipeline stages -- rewrite, retrieval, generation -- can
fail. Each failure yields exactly one `error` event and ends the stream;
there is no HTTP status code left to change at that point (the response
already committed to 200 when streaming began), so an explicit SSE event
is the only way to signal it (Handbook §6.2: never silently succeed).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.db.models import Chunk, Citation, Conversation, Message
from app.search.search_repo import SearchResultChunk
from app.services.generation.base import GenerationAdapter
from app.services.retrieval import RetrievalResult, retrieve
from app.services.rewrite import Turn, rewrite_query

logger = get_logger("chat")

REFUSAL_MESSAGE = (
    "I don't have information about that in the Contoso Corp knowledge base. "
    "I can only answer from the policy documents I've been given, so I'm not "
    "able to help with this one."
)

REWRITE_SYSTEM_PROMPT = (
    "You rewrite the user's latest question so it can be understood without "
    "the conversation history. Output only the rewritten question, nothing else."
)

CHAT_SYSTEM_PROMPT = (
    'You are the Contoso Corp internal knowledge assistant. Answer strictly and '
    'only from the excerpts under "Context" below -- never rely on outside '
    "knowledge, and never state a policy detail that isn't present in the "
    "context. When you use an excerpt, cite it inline as (Source: <section "
    "path>). If the context does not fully answer the question, say so plainly "
    "rather than guessing."
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _load_history(db: Session, conversation_id: uuid.UUID) -> list[Turn]:
    """Groups this conversation's Message rows into Turns (consecutive
    user -> assistant pairs), oldest first. rewrite_query() itself slices
    to the last HISTORY_TURNS, so the full history is passed through
    unsliced. A trailing user message with no assistant reply yet (e.g. a
    previous request that failed mid-stream) is dropped rather than
    included as a half-turn."""
    messages = (
        db.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at))
        .scalars()
        .all()
    )
    turns: list[Turn] = []
    pending_question: str | None = None
    for message in messages:
        if message.role == "user":
            pending_question = message.content
        elif message.role == "assistant" and pending_question is not None:
            turns.append(Turn(question=pending_question, answer=message.content))
            pending_question = None
    return turns


def _citation_payload(rank: int, chunk: SearchResultChunk) -> dict:
    return {
        "rank": rank,
        "document_id": chunk.document_id,
        "document_title": chunk.document_title,
        "section_path": chunk.section_path,
        "snippet": chunk.content,
        "reranker_score": chunk.reranker_score,
    }


def _resolve_chunk_id(db: Session, azure_doc_key: str) -> uuid.UUID | None:
    """Maps a search result back to its Postgres Chunk row via
    azure_doc_key (ingestion.py sets both to the same value -- confirmed
    in app/services/ingestion.py, not assumed). Nullable by design
    (Citation.chunk_id is ON DELETE SET NULL): if the chunk has since been
    removed by a re-index, the citation still stands on its own
    denormalized snapshot."""
    chunk = db.execute(select(Chunk).where(Chunk.azure_doc_key == azure_doc_key)).scalar_one_or_none()
    return chunk.id if chunk is not None else None


def _build_context_block(chunks: list[SearchResultChunk]) -> str:
    return "\n\n".join(f"[{chunk.section_path}]\n{chunk.content}" for chunk in chunks)


async def stream_chat_response(
    db: Session,
    conversation: Conversation,
    question: str,
    generation_adapter: GenerationAdapter,
) -> AsyncIterator[str]:
    history = _load_history(db, conversation.id)

    user_message = Message(conversation_id=conversation.id, role="user", content=question)
    db.add(user_message)
    db.commit()

    def _generate_fn(prompt: str) -> str:
        return asyncio.run(generation_adapter.complete(REWRITE_SYSTEM_PROMPT, prompt))

    try:
        standalone_query = await run_in_threadpool(rewrite_query, history, question, _generate_fn)
    except Exception as exc:  # noqa: BLE001 -- any rewrite failure must surface as one error event
        logger.error("rewrite_failed", conversation_id=str(conversation.id), error=str(exc))
        yield _sse("error", {"error": {"type": "internal_error", "message": "Query rewrite failed."}})
        return

    if history:
        user_message.rewritten_query = standalone_query
        db.commit()

    try:
        result: RetrievalResult = await run_in_threadpool(retrieve, db, standalone_query)
    except Exception as exc:  # noqa: BLE001
        logger.error("retrieval_failed", conversation_id=str(conversation.id), error=str(exc))
        yield _sse("error", {"error": {"type": "internal_error", "message": "Retrieval failed."}})
        return

    citations_payload = [_citation_payload(rank, chunk) for rank, chunk in enumerate(result.chunks, start=1)]
    yield _sse("citations", {"citations": citations_payload})

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        refused=result.refused,
        model=None if result.refused else generation_adapter.model_name,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    for rank, chunk in enumerate(result.chunks, start=1):
        db.add(
            Citation(
                message_id=assistant_message.id,
                chunk_id=_resolve_chunk_id(db, chunk.id),
                document_id=uuid.UUID(chunk.document_id),
                rank=rank,
                reranker_score=chunk.reranker_score,
                section_path=chunk.section_path,
                snippet=chunk.content,
            )
        )
    db.commit()

    full_text_parts: list[str] = []
    try:
        if result.refused:
            full_text_parts.append(REFUSAL_MESSAGE)
            yield _sse("token", {"delta": REFUSAL_MESSAGE})
        else:
            user_prompt = f"Context:\n{_build_context_block(result.chunks)}\n\nQuestion: {standalone_query}"
            async for delta in generation_adapter.stream(CHAT_SYSTEM_PROMPT, user_prompt):
                full_text_parts.append(delta)
                yield _sse("token", {"delta": delta})
    except Exception as exc:  # noqa: BLE001
        logger.error("generation_failed", conversation_id=str(conversation.id), error=str(exc))
        assistant_message.content = "".join(full_text_parts)
        db.commit()
        yield _sse("error", {"error": {"type": "internal_error", "message": "Generation failed."}})
        return

    assistant_message.content = "".join(full_text_parts)
    db.commit()

    yield _sse("done", {"message_id": str(assistant_message.id), "refused": result.refused})
