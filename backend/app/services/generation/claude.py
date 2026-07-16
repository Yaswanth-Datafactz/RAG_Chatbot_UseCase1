"""Claude implementation of the generation adapter (docs/plan.md Decision
#4), via Anthropic's async SDK client -- no live Anthropic credentials are
provisioned yet (backend/.env doesn't exist, only .env.example), so this
is exercised in tests via an injected fake client, never a live call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.services.generation.base import GenerationAdapter

MAX_TOKENS = 1024


class ClaudeGenerationAdapter(GenerationAdapter):
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self.model_name = model or settings.anthropic_model
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self.model_name,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
