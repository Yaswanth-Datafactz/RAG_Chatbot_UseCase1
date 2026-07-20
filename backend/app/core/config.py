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
    # Single production embedding deployment. text-embedding-3-small is not
    # used anywhere in this project -- no comparison deployment exists or
    # is planned; docs/phase-8.md's embedding-comparison item was cancelled
    # by explicit user decision, not merely blocked pending a deployment.
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = ""

    # Azure AI Foundry (model-inference API, distinct from the Azure
    # OpenAI SDK/endpoint above) -- DeepSeek-V3.2, added as a third
    # generation provider users can pick per-message (see
    # docs/plan.md Decisions Register #4). The target URI Azure AI Foundry
    # gives you already includes the full request path + api-version, so
    # it's stored as one complete endpoint rather than templated like the
    # Azure OpenAI SDK's bare resource host.
    azure_ai_foundry_endpoint: str = ""
    azure_ai_foundry_api_key: str = ""
    azure_ai_foundry_model: str = "DeepSeek-V3.2"

    # Generation provider: "claude", "azure_openai", or "deepseek" -- the
    # default when a chat request doesn't specify one (see docs/plan.md
    # Decisions Register #4). Users can override this per-message via
    # ChatMessageRequest.provider; GET /api/v1/models reports which
    # providers actually have credentials configured.
    generation_provider: str = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Retrieval tuning (see docs/plan.md Decisions Register #5, #6)
    retrieval_candidate_count: int = 20
    retrieval_top_k: int = 5
    # Calibrated in Phase 8 (docs/phase-8.md) against real Azure retrieval:
    # 9 in-corpus questions scored 2.811-3.555; the 6 deliberate
    # out-of-corpus gap questions (docs/phase-1.md) scored 1.650-2.310 --
    # a clean, non-overlapping separation gap of ~0.50. 2.6 sits inside
    # that gap (near its midpoint, 2.56), with a modest lean toward the
    # refuse-safe side, on the reasoning that a wrong-but-confident policy
    # answer is worse than an unnecessary refusal. The prior value (1.5)
    # let all 6 out-of-corpus questions through unrefused -- see
    # docs/phase-8.md for the full score table before treating this as
    # final; re-calibrate if real usage surfaces different score ranges.
    refusal_reranker_threshold: float = 2.6

    # Logging
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
