"""Azure OpenAI implementation of the generation adapter (docs/plan.md
Decision #4), via the async AzureOpenAI SDK client -- no live Azure
OpenAI chat credentials are provisioned yet (backend/.env doesn't exist,
only .env.example, and AZURE_OPENAI_CHAT_DEPLOYMENT is blank there), so
this is exercised in tests via an injected fake client, never a live call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncAzureOpenAI

from app.core.config import get_settings
from app.services.generation.base import GenerationAdapter


class AzureOpenAIGenerationAdapter(GenerationAdapter):
    def __init__(self, client: AsyncAzureOpenAI | None = None, deployment: str | None = None):
        settings = get_settings()
        self.model_name = deployment or settings.azure_openai_chat_deployment
        self._client = client or AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
