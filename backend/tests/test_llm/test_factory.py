"""Tests for LLM client factory."""
from __future__ import annotations

import pytest

from nl2sql.llm.base import LLMClient
from nl2sql.llm.claude_client import ClaudeClient
from nl2sql.llm.factory import create_llm_client
from nl2sql.llm.openai_client import OpenAIClient


class TestCreateLLMClient:
    def test_creates_claude_client(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "claude")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        client = create_llm_client()
        assert isinstance(client, LLMClient)
        assert isinstance(client, ClaudeClient)

    def test_creates_openai_client(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")

        client = create_llm_client()
        assert isinstance(client, LLMClient)
        assert isinstance(client, OpenAIClient)

    def test_creates_local_openai_compatible_client(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "local_openai_compatible")
        monkeypatch.setenv("OPENAI_API_KEY", "local-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OPENAI_MODEL", "local-model")

        client = create_llm_client()
        assert isinstance(client, LLMClient)
        assert isinstance(client, OpenAIClient)

    def test_unknown_provider_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "unknown_llm")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client()
