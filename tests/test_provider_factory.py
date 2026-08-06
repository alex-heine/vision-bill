import pytest
from unittest.mock import MagicMock
from vision_bill.config import LLMProviderEnum
from vision_bill.provider.factory import get_llm_provider
from vision_bill.provider.factory import get_llm_provider
from vision_bill.provider.llm.ollama import OllamaProvider


@pytest.mark.parametrize(
    "provider_enum, expected_class",
    [
        (LLMProviderEnum.OLLAMA, OllamaProvider),
    ],
)
async def test_get_llm_provider_success(settings, provider_enum, expected_class):
    """Test that the correct provider is returned for OLLAMA."""
    # The settings fixture from conftest already defaults to ollama in its nested config.
    provider = get_llm_provider(settings.llm)
    assert isinstance(provider, expected_class)


def test_get_llm_provider_failure():
    """Test that a ValueError is raised for unsupported providers."""
    # Mock settings object specifically to trigger the failure path in factory.py:8-15
    mock_settings = MagicMock()
    mock_settings.provider = "non_existent_provider"
    mock_settings.host = "http://localhost:11434"

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider(mock_settings)
