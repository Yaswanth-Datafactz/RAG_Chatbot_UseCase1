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
from unittest.mock import patch

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


def _suppress_real_current_run_and_make_conversation(title: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Shared setup for tests exercising retrieval.py's real "no current
    run" refusal path un-faked: temporarily un-marks whatever real
    current run exists (the dev database can hold one -- live Azure
    credentials configured after Phase 6) and creates a fresh
    conversation. Returns (conversation_id, previous_current_id) --
    pass previous_current_id to _restore_current_run in `finally`."""
    db = SessionLocal()
    try:
        previous_current = db.query(IngestionRun).filter(IngestionRun.is_current.is_(True)).one_or_none()
        previous_current_id = previous_current.id if previous_current is not None else None
        if previous_current is not None:
            previous_current.is_current = False
            db.commit()

        conversation = Conversation(title=title)
        db.add(conversation)
        db.commit()
        return conversation.id, previous_current_id
    finally:
        db.close()


def _restore_current_run(previous_current_id: uuid.UUID | None) -> None:
    if previous_current_id is None:
        return
    db = SessionLocal()
    try:
        restored = db.get(IngestionRun, previous_current_id)
        if restored is not None:
            restored.is_current = True
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
    """Exercises retrieval.py's real "no current ingestion run" refusal
    path un-faked (no Search/embeddings faking needed -- retrieval
    short-circuits before calling either). See docs/phase-7.md Deviations
    for why the real current run must be temporarily suppressed rather
    than assumed absent."""
    conversation_id, previous_current_id = _suppress_real_current_run_and_make_conversation("Refusal test")
    assert _no_current_ingestion_run_exists()

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
        _restore_current_run(previous_current_id)


def test_provider_in_request_body_selects_the_generation_adapter(client):
    """ChatMessageRequest.provider (the frontend's model picker) must
    reach get_generation_adapter() -- patches the factory itself (not
    dependency_overrides, since this test verifies the wiring *to* the
    factory, not what it returns) and reuses the same real "no current
    run" refusal path as the test above, so no Search/embeddings faking
    is needed and the adapter's own stream()/complete() never has to run
    for this to prove the request body reached the right place."""
    conversation_id, previous_current_id = _suppress_real_current_run_and_make_conversation("Provider selection test")

    try:
        with patch("app.api.v1.chat.get_generation_adapter", return_value=_UnusedGenerationAdapter()) as mock_factory:
            response = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={"content": "What is the executive severance policy?", "provider": "deepseek"},
                headers=API_KEY_HEADER,
            )

        assert response.status_code == 200
        mock_factory.assert_called_once_with("deepseek")
    finally:
        _cleanup_conversation(conversation_id)
        _restore_current_run(previous_current_id)


def test_omitted_provider_falls_back_to_the_configured_default(client):
    conversation_id, previous_current_id = _suppress_real_current_run_and_make_conversation("Default provider test")

    try:
        with patch("app.api.v1.chat.get_generation_adapter", return_value=_UnusedGenerationAdapter()) as mock_factory:
            response = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={"content": "What is the executive severance policy?"},
                headers=API_KEY_HEADER,
            )

        assert response.status_code == 200
        mock_factory.assert_called_once_with(None)
    finally:
        _cleanup_conversation(conversation_id)
        _restore_current_run(previous_current_id)
