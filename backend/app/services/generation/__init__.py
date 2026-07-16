"""Generation-provider selection (docs/plan.md Decision #4):
GENERATION_PROVIDER picks Claude or Azure OpenAI -- a config change, not a
rewrite.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.generation.base import GenerationAdapter

_PROVIDERS = {"claude", "azure_openai"}


def get_generation_adapter(provider: str | None = None) -> GenerationAdapter:
    settings = get_settings()
    selected = (provider or settings.generation_provider).lower()

    if selected == "claude":
        from app.services.generation.claude import ClaudeGenerationAdapter

        return ClaudeGenerationAdapter()
    if selected == "azure_openai":
        from app.services.generation.azure_openai import AzureOpenAIGenerationAdapter

        return AzureOpenAIGenerationAdapter()

    raise ValueError(f"Unknown GENERATION_PROVIDER: {selected!r}. Expected one of {sorted(_PROVIDERS)}.")
