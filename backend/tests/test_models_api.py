"""Route-level tests for GET /models: each provider's `available` flag
reflects real configured credentials (checked dynamically against
get_settings(), not hardcoded -- this dev environment's actual .env
determines what's really available, and that can change)."""

from app.core.config import get_settings

API_KEY_HEADER = {"X-API-Key": get_settings().api_key}


def test_list_models_requires_api_key(client):
    response = client.get("/api/v1/models")

    assert response.status_code == 401


def test_list_models_returns_all_three_known_providers_with_real_availability(client):
    response = client.get("/api/v1/models", headers=API_KEY_HEADER)
    assert response.status_code == 200

    body = response.json()
    by_id = {m["id"]: m for m in body}
    assert set(by_id) == {"claude", "azure_openai", "deepseek"}

    settings = get_settings()
    assert by_id["claude"]["available"] == bool(settings.anthropic_api_key)
    assert by_id["azure_openai"]["available"] == bool(
        settings.azure_openai_api_key and settings.azure_openai_chat_deployment
    )
    assert by_id["deepseek"]["available"] == bool(settings.azure_ai_foundry_api_key and settings.azure_ai_foundry_endpoint)

    # Exactly one provider is marked as the configured default.
    defaults = [m["id"] for m in body if m["is_default"]]
    assert defaults == [settings.generation_provider.lower()]

    assert by_id["deepseek"]["label"] == settings.azure_ai_foundry_model
