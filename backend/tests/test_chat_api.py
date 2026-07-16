"""Route-level test for POST /conversations/{id}/messages: the generation
adapter is overridden via FastAPI's dependency_overrides (no live LLM
credentials are provisioned); the request deliberately runs with no
current ingestion run in Postgres, so retrieval.retrieve() takes its
real, un-faked "no corpus to answer from" refusal path -- this proves the
route, services/chat.py, and retrieval.py's refusal gate all wire
together correctly end to end, without needing to fake Search/embeddings
for this particular test.
"""

import json
import uuid

from sqlalchemy import select

from app.api.v1.chat import _default_generation_adapter
from app.core.config import get_settings
from app.db.models import Conversation, IngestionRun
from app.db.session import SessionLocal
from app.main import app
from app.services.generation.base import GenerationAdapter

API_KEY_HEADER = {"X-API-Key": get_settings().api_key}


class _UnusedGenerationAdapter(GenerationAdapter):
    """Raises if ever called -- the refusal path must never reach generation."""

    model_name = "unused"

    async def complete(self, system_prompt, user_prompt):
        raise AssertionError("complete() must not be called when there is no current ingestion run")

    async def stream(self, system_prompt, user_prompt):
        raise AssertionError("stream() must not be called when there is no current ingestion run")
        yield ""  # pragma: no cover -- makes this an async generator function


def _parse_sse_stream(text: str) -> list[tuple[str, dict]]:
    events = []
    for raw in text.split("\n\n"):
        if not raw.strip():
            continue
        lines = raw.strip("\n").split("\n")
        event_name = next(line for line in lines if line.startswith("event: "))[len("event: ") :]
        data_line = next(line for line in lines if line.startswith("data: "))[len("data: ") :]
        events.append((event_name, json.loads(data_line)))
    return events


def _no_current_ingestion_run_exists() -> bool:
    db = SessionLocal()
    try:
        return db.execute(select(IngestionRun).where(IngestionRun.is_current.is_(True))).scalar_one_or_none() is None
    finally:
        db.close()


def _cleanup_conversation(conversation_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            db.delete(conversation)
            db.commit()
    finally:
        db.close()


def test_post_message_requires_api_key(client):
    response = client.post(f"/api/v1/conversations/{uuid.uuid4()}/messages", json={"content": "hi"})

    assert response.status_code == 401


def test_post_message_404_for_unknown_conversation(client):
    response = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages", json={"content": "hi"}, headers=API_KEY_HEADER
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"


def test_post_message_streams_refusal_end_to_end_when_no_corpus_is_indexed(client):
    assert _no_current_ingestion_run_exists(), (
        "This test relies on no ingestion run being current, to exercise "
        "retrieval.py's real refusal path without faking Search/embeddings."
    )

    db = SessionLocal()
    try:
        conversation = Conversation(title="Refusal test")
        db.add(conversation)
        db.commit()
        conversation_id = conversation.id
    finally:
        db.close()

    app.dependency_overrides[_default_generation_adapter] = lambda: _UnusedGenerationAdapter()
    try:
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "What is the executive severance policy?"},
            headers=API_KEY_HEADER,
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_stream(response.text)
        assert [name for name, _ in events] == ["citations", "token", "done"]
        assert events[0][1] == {"citations": []}
        assert "don't have information" in events[1][1]["delta"]
        assert events[2][1]["refused"] is True
    finally:
        app.dependency_overrides.pop(_default_generation_adapter, None)
        _cleanup_conversation(conversation_id)
