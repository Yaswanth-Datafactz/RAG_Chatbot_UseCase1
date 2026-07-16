"""No live Anthropic credentials are provisioned (backend/.env doesn't
exist). Verifies ClaudeGenerationAdapter constructs correct requests and
correctly bridges the SDK's async-context-manager streaming shape into a
plain async generator of text -- against a fake AsyncAnthropic client,
never a live call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generation.claude import ClaudeGenerationAdapter


class _FakeMessageStream:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @property
    def text_stream(self):
        return self._agen()

    async def _agen(self):
        for chunk in self._chunks:
            yield chunk


def _fake_anthropic_client(complete_text="rewritten question", stream_chunks=None):
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text=complete_text)])
    )
    client.messages.stream = MagicMock(return_value=_FakeMessageStream(stream_chunks or ["Hello", " world"]))
    return client


@pytest.mark.asyncio
async def test_complete_calls_client_with_model_system_and_user_message():
    fake_client = _fake_anthropic_client(complete_text="Standalone question?")
    adapter = ClaudeGenerationAdapter(client=fake_client, model="claude-test-model")

    result = await adapter.complete("system instructions", "rewrite this")

    assert result == "Standalone question?"
    fake_client.messages.create.assert_awaited_once()
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["model"] == "claude-test-model"
    assert kwargs["system"] == "system instructions"
    assert kwargs["messages"] == [{"role": "user", "content": "rewrite this"}]


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_in_order():
    fake_client = _fake_anthropic_client(stream_chunks=["Hel", "lo", " world"])
    adapter = ClaudeGenerationAdapter(client=fake_client, model="claude-test-model")

    deltas = [chunk async for chunk in adapter.stream("system", "question")]

    assert deltas == ["Hel", "lo", " world"]
    fake_client.messages.stream.assert_called_once()
    _, kwargs = fake_client.messages.stream.call_args
    assert kwargs["model"] == "claude-test-model"
    assert kwargs["system"] == "system"


def test_model_name_defaults_from_settings_when_not_provided():
    adapter = ClaudeGenerationAdapter(client=_fake_anthropic_client())

    assert adapter.model_name  # non-empty, pulled from settings.anthropic_model
