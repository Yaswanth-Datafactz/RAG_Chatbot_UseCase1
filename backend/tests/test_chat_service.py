"""Tests for services/chat.py's orchestration: the SSE event protocol
(order + JSON shape) and its DB persistence side effects.

services/chat.py commits for real as it progresses (the user message is
persisted before rewrite/retrieval even start, and the assistant message
is persisted right after retrieval so citations survive even if
generation itself fails) -- there is no single outer transaction to roll
back, so these tests use plain SessionLocal() sessions against the real
local Postgres and clean up explicitly in `finally`, exactly like
test_ingestion.py.

retrieval.retrieve() itself is not exercised here (that's test_retrieval.py's
job); app.services.chat.retrieve is patched directly so these tests
control exactly what comes back from "retrieval" and focus on what chat.py
does with it.
"""

import json
import uuid
from unittest.mock import patch

import pytest

from app.db.models import Chunk, Citation, Conversation, Document, IngestionRun, Message
from app.db.session import SessionLocal
from app.search.search_repo import SearchResultChunk
from app.services import chat as chat_service
from app.services.generation.base import GenerationAdapter
from app.services.retrieval import RetrievalResult


class FakeGenerationAdapter(GenerationAdapter):
    def __init__(self, complete_response="standalone rewritten question", stream_chunks=None, raise_after=None):
        self.model_name = "fake-model-v1"
        self.complete_calls: list[tuple[str, str]] = []
        self.stream_calls: list[tuple[str, str]] = []
        self._complete_response = complete_response
        self._stream_chunks = stream_chunks if stream_chunks is not None else ["Hello", " there"]
        self._raise_after = raise_after

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.complete_calls.append((system_prompt, user_prompt))
        return self._complete_response

    async def stream(self, system_prompt: str, user_prompt: str):
        self.stream_calls.append((system_prompt, user_prompt))
        for i, chunk in enumerate(self._stream_chunks):
            if self._raise_after is not None and i == self._raise_after:
                raise RuntimeError("simulated generation failure")
            yield chunk


def _parse_sse(raw: str) -> tuple[str, dict]:
    lines = raw.strip("\n").split("\n")
    event_name = next(line for line in lines if line.startswith("event: "))[len("event: ") :]
    data_line = next(line for line in lines if line.startswith("data: "))[len("data: ") :]
    return event_name, json.loads(data_line)


async def _collect(agen):
    return [chunk async for chunk in agen]


def _make_fixture():
    """A Conversation plus a current IngestionRun/Document/Chunk, so
    citation persistence can resolve a real chunk_id via azure_doc_key."""
    db = SessionLocal()
    try:
        conversation = Conversation(title="Test conversation")
        run = IngestionRun(status="succeeded", embedding_model="fake", is_current=True, doc_count=1, chunk_count=1)
        document = Document(
            source_filename="fixture.md",
            title="Fixture Policy One",
            doc_type="markdown",
            sha256=f"sha-{uuid.uuid4()}",
            byte_size=10,
        )
        db.add_all([conversation, run, document])
        db.flush()
        chunk = Chunk(
            document_id=document.id,
            ingestion_run_id=run.id,
            chunk_index=0,
            section_path="Fixture Policy One > Section A",
            content="Full-time employees accrue 15 days of PTO per year.",
            token_count=10,
            azure_doc_key=f"{run.id}_{document.id}_0",
        )
        db.add(chunk)
        db.commit()
        ids = {
            "conversation_id": conversation.id,
            "run_id": run.id,
            "document_id": document.id,
            "chunk_id": chunk.id,
            "azure_doc_key": chunk.azure_doc_key,
        }
        return ids
    finally:
        db.close()


def _cleanup(ids: dict) -> None:
    db = SessionLocal()
    try:
        conversation = db.get(Conversation, ids["conversation_id"])
        if conversation is not None:
            db.delete(conversation)  # cascades messages -> citations
        run = db.get(IngestionRun, ids["run_id"])
        if run is not None:
            db.delete(run)  # cascades chunks
        document = db.get(Document, ids["document_id"])
        if document is not None:
            db.delete(document)
        db.commit()
    finally:
        db.close()


def _search_result(azure_doc_key: str, document_id: uuid.UUID, section_path="Section A", reranker_score=3.2) -> SearchResultChunk:
    return SearchResultChunk(
        id=azure_doc_key,
        content="Full-time employees accrue 15 days of PTO per year.",
        section_path=section_path,
        document_id=str(document_id),
        document_title="Fixture Policy One",
        ingestion_run_id="run-1",
        chunk_index=0,
        score=0.9,
        reranker_score=reranker_score,
    )


@pytest.mark.asyncio
async def test_refusal_path_sends_empty_citations_then_refusal_message_then_done():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter()

        refused_result = RetrievalResult(chunks=[], refused=True, top_reranker_score=0.4)
        with patch.object(chat_service, "retrieve", return_value=refused_result):
            events = [_parse_sse(raw) for raw in await _collect(
                chat_service.stream_chat_response(db, conversation, "what about executive severance?", adapter)
            )]

        assert [name for name, _ in events] == ["citations", "token", "done"]
        assert events[0][1] == {"citations": []}
        assert events[1][1] == {"delta": chat_service.REFUSAL_MESSAGE}
        assert events[2][1]["refused"] is True
        assert adapter.stream_calls == []  # no generation call was made

        db.expire_all()
        assistant = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "assistant")
            .one()
        )
        assert assistant.refused is True
        assert assistant.content == chat_service.REFUSAL_MESSAGE
        assert assistant.model is None
        assert db.query(Citation).filter(Citation.message_id == assistant.id).count() == 0
        db.close()
    finally:
        _cleanup(ids)


@pytest.mark.asyncio
async def test_success_path_sends_citations_before_tokens_then_done_and_persists():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter(stream_chunks=["The", " policy", " is..."])

        matching_chunk = _search_result(ids["azure_doc_key"], ids["document_id"], reranker_score=3.5)
        orphaned_chunk = _search_result("no-such-azure-key", ids["document_id"], section_path="Section B", reranker_score=3.1)
        result = RetrievalResult(chunks=[matching_chunk, orphaned_chunk], refused=False, top_reranker_score=3.5)

        with patch.object(chat_service, "retrieve", return_value=result):
            events = [_parse_sse(raw) for raw in await _collect(
                chat_service.stream_chat_response(db, conversation, "what is the PTO policy?", adapter)
            )]

        names = [name for name, _ in events]
        assert names == ["citations", "token", "token", "token", "done"]
        assert names.index("citations") < names.index("token")

        citations_data = events[0][1]["citations"]
        assert [c["rank"] for c in citations_data] == [1, 2]
        assert citations_data[0]["document_id"] == str(ids["document_id"])
        assert citations_data[0]["section_path"] == "Section A"
        assert citations_data[0]["reranker_score"] == 3.5

        token_deltas = [data["delta"] for name, data in events if name == "token"]
        assert token_deltas == ["The", " policy", " is..."]

        done_data = events[-1][1]
        assert done_data["refused"] is False
        uuid.UUID(done_data["message_id"])  # parses cleanly

        db.expire_all()
        assistant = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "assistant")
            .one()
        )
        assert assistant.content == "The policy is..."
        assert assistant.refused is False
        assert assistant.model == "fake-model-v1"

        citations = db.query(Citation).filter(Citation.message_id == assistant.id).order_by(Citation.rank).all()
        assert len(citations) == 2
        assert citations[0].chunk_id == ids["chunk_id"]
        assert citations[0].document_id == ids["document_id"]
        assert citations[1].chunk_id is None  # no matching azure_doc_key -- resolves to None, not an error
        db.close()
    finally:
        _cleanup(ids)


@pytest.mark.asyncio
async def test_history_triggers_rewrite_and_persists_rewritten_query_on_the_user_message():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        prior_user = Message(conversation_id=ids["conversation_id"], role="user", content="What is the PTO policy?")
        prior_assistant = Message(
            conversation_id=ids["conversation_id"], role="assistant", content="Full-time employees accrue 15 days/year."
        )
        db.add_all([prior_user, prior_assistant])
        db.commit()

        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter(complete_response="What is the PTO policy for contractors?")

        captured_queries = []

        def _fake_retrieve(db_arg, query, **kwargs):
            captured_queries.append(query)
            chunk = _search_result(ids["azure_doc_key"], ids["document_id"])
            return RetrievalResult(chunks=[chunk], refused=False, top_reranker_score=3.0)

        with patch.object(chat_service, "retrieve", side_effect=_fake_retrieve):
            await _collect(chat_service.stream_chat_response(db, conversation, "What about for contractors?", adapter))

        assert len(adapter.complete_calls) == 1
        system_prompt, user_prompt = adapter.complete_calls[0]
        assert system_prompt == chat_service.REWRITE_SYSTEM_PROMPT
        assert "What is the PTO policy?" in user_prompt
        assert "What about for contractors?" in user_prompt

        assert captured_queries == ["What is the PTO policy for contractors?"]

        db.expire_all()
        user_messages = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "user")
            .order_by(Message.created_at)
            .all()
        )
        newest_user_message = user_messages[-1]
        assert newest_user_message.content == "What about for contractors?"
        assert newest_user_message.rewritten_query == "What is the PTO policy for contractors?"
        db.close()
    finally:
        _cleanup(ids)


@pytest.mark.asyncio
async def test_no_history_skips_rewrite_generation_call():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter()
        result = RetrievalResult(chunks=[], refused=True, top_reranker_score=None)

        with patch.object(chat_service, "retrieve", return_value=result):
            await _collect(chat_service.stream_chat_response(db, conversation, "What is the PTO policy?", adapter))

        assert adapter.complete_calls == []  # no history -> rewrite_query() never calls generate_fn

        db.expire_all()
        user_message = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "user")
            .one()
        )
        assert user_message.rewritten_query is None
        db.close()
    finally:
        _cleanup(ids)


@pytest.mark.asyncio
async def test_generation_failure_mid_stream_yields_error_event_persists_partial_content_no_done():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter(stream_chunks=["Hello", " world"], raise_after=1)
        chunk = _search_result(ids["azure_doc_key"], ids["document_id"])
        result = RetrievalResult(chunks=[chunk], refused=False, top_reranker_score=3.0)

        with patch.object(chat_service, "retrieve", return_value=result):
            events = [_parse_sse(raw) for raw in await _collect(
                chat_service.stream_chat_response(db, conversation, "what is the PTO policy?", adapter)
            )]

        names = [name for name, _ in events]
        assert names == ["citations", "token", "error"]
        assert events[1][1] == {"delta": "Hello"}
        assert events[2][1]["error"]["type"] == "internal_error"

        db.expire_all()
        assistant = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "assistant")
            .one()
        )
        assert assistant.content == "Hello"  # partial content persisted even though generation failed
        db.close()
    finally:
        _cleanup(ids)


@pytest.mark.asyncio
async def test_retrieval_failure_yields_only_an_error_event_no_citations():
    ids = _make_fixture()
    try:
        db = SessionLocal()
        conversation = db.get(Conversation, ids["conversation_id"])
        adapter = FakeGenerationAdapter()

        with patch.object(chat_service, "retrieve", side_effect=RuntimeError("simulated retrieval failure")):
            events = [_parse_sse(raw) for raw in await _collect(
                chat_service.stream_chat_response(db, conversation, "what is the PTO policy?", adapter)
            )]

        assert [name for name, _ in events] == ["error"]
        assert events[0][1]["error"]["type"] == "internal_error"

        db.expire_all()
        # The user's question is still persisted even though retrieval failed.
        user_message = (
            db.query(Message)
            .filter(Message.conversation_id == ids["conversation_id"], Message.role == "user")
            .one()
        )
        assert user_message.content == "what is the PTO policy?"
        assert db.query(Message).filter(Message.conversation_id == ids["conversation_id"], Message.role == "assistant").count() == 0
        db.close()
    finally:
        _cleanup(ids)
