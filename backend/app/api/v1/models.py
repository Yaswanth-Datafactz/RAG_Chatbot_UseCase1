"""GET /models -- lists the generation providers this deployment knows
about (docs/plan.md Decisions Register #4), each with whether it
actually has credentials configured. The frontend's model picker reads
this rather than hardcoding a provider list, so it never offers a
provider that would just fail on first use -- and each `id` here is
exactly what a client sends back as ChatMessageRequest.provider."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.security import require_api_key
from app.schemas.models import ModelOut

router = APIRouter(
    prefix="/models",
    tags=["models"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)


@router.get("", response_model=list[ModelOut])
def list_models() -> list[ModelOut]:
    settings = get_settings()
    default = settings.generation_provider.lower()

    candidates = [
        ("claude", "Claude", bool(settings.anthropic_api_key)),
        (
            "azure_openai",
            settings.azure_openai_chat_deployment or "Azure OpenAI",
            bool(settings.azure_openai_api_key and settings.azure_openai_chat_deployment),
        ),
        (
            "deepseek",
            settings.azure_ai_foundry_model,
            bool(settings.azure_ai_foundry_api_key and settings.azure_ai_foundry_endpoint),
        ),
    ]
    return [
        ModelOut(id=provider_id, label=label, available=available, is_default=provider_id == default)
        for provider_id, label, available in candidates
    ]
