"""Embedding client -- Azure OpenAI text-embedding-3-small by default,
pluggable to text-embedding-3-large (docs/plan.md Decision #3).

Both v3 embedding models are requested at a fixed 1536-dim output (the
`dimensions` parameter both support) so Azure AI Search's vector field
dimensionality never has to change to compare them in Phase 8 -- see
docs/phase-2.md for why the index is built around a fixed dimension.
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
