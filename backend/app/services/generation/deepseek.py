"""DeepSeek-V3.2 implementation of the generation adapter, served via
Azure AI Foundry's model-inference API (docs/plan.md Decisions Register
#4) -- a different shape from the Azure OpenAI SDK/endpoint used
elsewhere in this codebase: the deployment is serverless/MaaS, so the
model name goes in the JSON body (`"model": "DeepSeek-V3.2"`) rather than
the URL path, and there's no first-party Python SDK dependency already
in this project for it. Implemented directly over `httpx.AsyncClient`
instead of adding a new SDK dependency for one model.

The exact request/response shape below (auth header, streaming SSE
format, the trailing choices-less usage chunk, the `[DONE]` sentinel) was
confirmed with real calls against the live endpoint before writing this,
not assumed from documentation -- both a plain and a streaming call,
using the real deployment credentials.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services.generation.base import GenerationAdapter

MAX_TOKENS = 1024

# httpx defaults to a 5s timeout on every phase (connect/read/write/pool) if
# none is given. DeepSeek-V3.2 is a reasoning model with a highly variable
# time-to-first-token -- especially once the conversation history and
# retrieved context grow the prompt -- so the 5s default read timeout was
# tripping mid-conversation even though the request was still in flight, not
# actually stuck. The OpenAI SDK client used for the Azure OpenAI path
# doesn't hit this because it defaults to a 10-minute timeout with built-in
# retries; this raw httpx client has neither, so it needs an explicit one.
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)


class DeepSeekGenerationAdapter(GenerationAdapter):
    def __init__(self, client: httpx.AsyncClient | None = None, model: str | None = None):
        settings = get_settings()
        self.model_name = model or settings.azure_ai_foundry_model
        self._endpoint = settings.azure_ai_foundry_endpoint
        self._client = client or httpx.AsyncClient(
            headers={"Content-Type": "application/json", "api-key": settings.azure_ai_foundry_api_key},
            timeout=REQUEST_TIMEOUT,
        )

    def _body(self, system_prompt: str, user_prompt: str, *, stream: bool) -> dict:
        return {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": MAX_TOKENS,
            "stream": stream,
        }

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.post(self._endpoint, json=self._body(system_prompt, user_prompt, stream=False))
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST", self._endpoint, json=self._body(system_prompt, user_prompt, stream=True)
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue  # a stray non-JSON keep-alive line -- skip rather than abort the whole stream
                choices = chunk.get("choices") or []
                if not choices:
                    continue  # the trailing usage-only chunk carries no choices
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    yield delta
