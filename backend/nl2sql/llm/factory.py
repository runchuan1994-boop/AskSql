"""LLM client factory."""
from __future__ import annotations

from ..config import Settings
from .base import LLMClient
from .claude_client import ClaudeClient
from .openai_client import OpenAIClient


def create_llm_client() -> LLMClient:
    """Create an LLM client based on settings.llm_provider."""
    settings = Settings()
    provider = settings.llm_provider

    if provider == "claude":
        return ClaudeClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    elif provider == "openai":
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    elif provider == "local_openai_compatible":
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
