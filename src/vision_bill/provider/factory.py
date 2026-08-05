# llm/factory.py

from ..config import LLMProviderEnum, LLMSettings

from .llm.base import LLMProvider


def get_llm_provider(llm_settings: LLMSettings) -> LLMProvider:
    provider = llm_settings.provider

    if provider == LLMProviderEnum.OLLAMA:
        from .llm.ollama import OllamaProvider
        return OllamaProvider(host=llm_settings.host)

    raise ValueError(f"Unsupported LLM provider: {provider}")
