"""No live Azure OpenAI chat credentials are provisioned (backend/.env
doesn't exist, AZURE_OPENAI_CHAT_DEPLOYMENT is blank in .env.example).
Verifies AzureOpenAIGenerationAdapter constructs correct requests and
correctly skips chunks with no delta content while streaming -- against a
fake AsyncAzureOpenAI client, never a live call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generation.azure_openai import AzureOpenAIGenerationAdapter


def _completion_response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _stream_chunk(delta_text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=delta_text))])


async def _fake_stream(chunks):
    for chunk in chunks:
        yield _stream_chunk(chunk)


def _fake_azure_client(complete_text="Standalone question?", stream_chunks=None):
    client = MagicMock()

    async def _create(*, model, messages, stream=False):
        if stream:
            return _fake_stream(stream_chunks or ["Hello", " world"])
        return _completion_response(complete_text)

    client.chat.completions.create = AsyncMock(side_effect=_create)
    return client


@pytest.mark.asyncio
async def test_complete_calls_client_with_deployment_system_and_user_messages():
    fake_client = _fake_azure_client(complete_text="Standalone question?")
    adapter = AzureOpenAIGenerationAdapter(client=fake_client, deployment="gpt-4o-test")

    result = await adapter.complete("system instructions", "rewrite this")

    assert result == "Standalone question?"
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-test"
    assert kwargs["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "rewrite this"},
    ]


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_in_order():
    fake_client = _fake_azure_client(stream_chunks=["Hel", "lo", " world"])
    adapter = AzureOpenAIGenerationAdapter(client=fake_client, deployment="gpt-4o-test")

    deltas = [chunk async for chunk in adapter.stream("system", "question")]

    assert deltas == ["Hel", "lo", " world"]


@pytest.mark.asyncio
async def test_stream_skips_chunks_with_no_delta_content():
    async def _stream_with_gaps():
        yield _stream_chunk("Hello")
        yield SimpleNamespace(choices=[])
        yield _stream_chunk(None)
        yield _stream_chunk(" world")

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_stream_with_gaps())
    adapter = AzureOpenAIGenerationAdapter(client=fake_client, deployment="gpt-4o-test")

    deltas = [chunk async for chunk in adapter.stream("s", "u")]

    assert deltas == ["Hello", " world"]
