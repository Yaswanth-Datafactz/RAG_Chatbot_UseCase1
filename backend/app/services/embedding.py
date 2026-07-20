"""Embedding client -- Azure OpenAI text-embedding-3-large (docs/plan.md
Decisions Register #3). text-embedding-3-small is not used anywhere in
this project; no comparison deployment exists or is planned (removed by
explicit user decision -- see docs/phase-8.md's item 3, now cancelled
rather than deferred).

Requested at a fixed 1536-dim output (the `dimensions` parameter this
model supports, truncating its native 3072-dim output) because Azure AI
Search's vector field was built around that dimension -- see
docs/phase-2.md. Changing this now would require a real index-schema
migration, not just a config change.
"""

from __future__ import annotations

from openai import AzureOpenAI

from app.core.config import get_settings

EMBEDDING_DIMENSIONS = 1536


class EmbeddingClient:
    def __init__(self, deployment: str | None = None, client: AzureOpenAI | None = None):
        settings = get_settings()
        self.deployment_name = deployment or settings.azure_openai_embedding_deployment
        self._client = client or AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.deployment_name,
            input=texts,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return [item.embedding for item in response.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]
