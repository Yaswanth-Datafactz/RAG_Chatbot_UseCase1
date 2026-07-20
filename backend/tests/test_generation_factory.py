import pytest

from app.services.generation import get_generation_adapter
from app.services.generation.azure_openai import AzureOpenAIGenerationAdapter
from app.services.generation.claude import ClaudeGenerationAdapter
from app.services.generation.deepseek import DeepSeekGenerationAdapter


def test_claude_provider_returns_claude_adapter():
    adapter = get_generation_adapter(provider="claude")

    assert isinstance(adapter, ClaudeGenerationAdapter)


def test_azure_openai_provider_returns_azure_adapter():
    adapter = get_generation_adapter(provider="azure_openai")

    assert isinstance(adapter, AzureOpenAIGenerationAdapter)


def test_deepseek_provider_returns_deepseek_adapter():
    adapter = get_generation_adapter(provider="deepseek")

    assert isinstance(adapter, DeepSeekGenerationAdapter)


def test_provider_name_is_case_insensitive():
    adapter = get_generation_adapter(provider="Claude")

    assert isinstance(adapter, ClaudeGenerationAdapter)


def test_unknown_provider_raises_value_error():
    with pytest.raises(ValueError, match="Unknown GENERATION_PROVIDER"):
        get_generation_adapter(provider="not-a-real-provider")


def test_defaults_to_settings_generation_provider_when_not_specified():
    from app.core.config import get_settings

    adapter = get_generation_adapter()

    assert isinstance(adapter, ClaudeGenerationAdapter) == (get_settings().generation_provider.lower() == "claude")
