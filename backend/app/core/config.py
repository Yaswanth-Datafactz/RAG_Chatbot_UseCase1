"""Environment-driven application settings (Handbook §6.2: config via env vars)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://rag_chatbot:rag_chatbot_dev@localhost:5432/rag_chatbot"

    # API auth
    api_key: str = "changeme-dev-key"

    # CORS (comma-separated origins)
    cors_origins: str = "http://localhost:5173"

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "rag-chatbot-chunks"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_embedding_deployment_large: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = ""

    # Generation provider: "claude" or "azure_openai" (see docs/plan.md Decisions Register #4)
    generation_provider: str = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Retrieval tuning (see docs/plan.md Decisions Register #5, #6)
    retrieval_candidate_count: int = 20
    retrieval_top_k: int = 5
    # PROVISIONAL -- TODO-calibrate-in-Phase-8. Azure's semantic reranker
    # score ranges 0-4; this cutoff has not been empirically measured
    # against the Phase 8 test-question set or the deliberate
    # out-of-corpus gaps (docs/phase-1.md). Do not treat this value as
    # justified until Phase 8 records real calibration data.
    refusal_reranker_threshold: float = 1.5

    # Logging
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
