"""DeepSeekGenerationAdapter tests against a faked httpx transport (never
a live call) -- httpx.MockTransport intercepts the request and returns a
canned response shaped exactly like the real Azure AI Foundry endpoint's
output (confirmed with real calls before writing app/services/generation/
deepseek.py; see that module's docstring), including the streaming
format's trailing choices-less usage chunk and the `[DONE]` sentinel.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.generation.deepseek import DeepSeekGenerationAdapter


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_complete_posts_expected_body_and_parses_the_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Standalone question?"}}]})

    adapter = DeepSeekGenerationAdapter(client=_client_with_handler(handler), model="DeepSeek-V3.2-test")

    result = await adapter.complete("system instructions", "rewrite this")

    assert result == "Standalone question?"
    assert captured["body"]["model"] == "DeepSeek-V3.2-test"
    assert captured["body"]["stream"] is False
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "rewrite this"},
    ]


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_in_order_and_stops_at_done():
    sse_body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":null},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":1,"total_tokens":2,"completion_tokens":1}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=sse_body.encode(), headers={"content-type": "text/event-stream"})

    adapter = DeepSeekGenerationAdapter(client=_client_with_handler(handler), model="DeepSeek-V3.2-test")

    deltas = [chunk async for chunk in adapter.stream("system", "question")]

    assert deltas == ["Hel", "lo", " world"]


@pytest.mark.asyncio
async def test_complete_raises_for_a_non_2xx_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "DeploymentNotFound"}})

    adapter = DeepSeekGenerationAdapter(client=_client_with_handler(handler), model="not-a-real-deployment")

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.complete("system", "question")


def test_model_name_defaults_to_settings_when_not_overridden():
    from app.core.config import get_settings

    adapter = DeepSeekGenerationAdapter()

    assert adapter.model_name == get_settings().azure_ai_foundry_model


def test_default_client_sends_the_configured_api_key_header():
    from app.core.config import get_settings

    adapter = DeepSeekGenerationAdapter()  # no injected client -- builds its own

    assert adapter._client.headers["api-key"] == get_settings().azure_ai_foundry_api_key
