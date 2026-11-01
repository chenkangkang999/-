"""LLM clients with explicit configuration; no automatic fake provider."""
from agents.contracts import LLMClient, LLMResponse, LLMUsage
from agents.llm.client import LLMConfigurationError, LLMProviderError, OpenAICompatibleClient


def get_llm_client() -> LLMClient:
    return OpenAICompatibleClient.from_env()


__all__ = [
    "LLMClient", "LLMResponse", "LLMUsage", "LLMConfigurationError",
    "LLMProviderError", "OpenAICompatibleClient", "get_llm_client",
]
