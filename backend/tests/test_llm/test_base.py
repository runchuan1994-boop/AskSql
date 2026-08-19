"""Tests for LLM base classes."""
from __future__ import annotations

from abc import abstractmethod

import pytest

from nl2sql.llm.base import ChatChunk, ChatResponse, LLMClient
from nl2sql.llm.message import Message, MessageRole, ToolCall


class TestChatResponse:
    def test_creation_with_content(self):
        resp = ChatResponse(content="Hello", model="gpt-4")
        assert resp.content == "Hello"
        assert resp.model == "gpt-4"
        assert resp.tool_calls == []
        assert resp.usage == {}

    def test_creation_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="exec_sql", arguments={"sql": "SELECT 1"})
        resp = ChatResponse(content="", tool_calls=[tc], model="claude")
        assert resp.content == ""
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "exec_sql"

    def test_usage_default_empty(self):
        resp = ChatResponse(content="hi")
        assert resp.usage == {}


class TestChatChunk:
    def test_content_delta_default(self):
        chunk = ChatChunk()
        assert chunk.content_delta == ""
        assert chunk.tool_call_delta is None
        assert chunk.done is False

    def test_done_chunk(self):
        chunk = ChatChunk(done=True)
        assert chunk.done is True
        assert chunk.content_delta == ""


class TestLLMClient:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            LLMClient()

    def test_has_chat_method(self):
        assert hasattr(LLMClient, "chat")
        assert callable(getattr(LLMClient, "chat"))

    def test_has_chat_stream_method(self):
        assert hasattr(LLMClient, "chat_stream")
        assert callable(getattr(LLMClient, "chat_stream"))

    def test_concrete_subclass_can_be_instantiated(self):
        class ConcreteClient(LLMClient):
            def chat(self, messages, tools=None, temperature=0.0, max_tokens=4096):
                return ChatResponse(content="hi")

            def chat_stream(self, messages, tools=None, temperature=0.0, max_tokens=4096):
                yield ChatChunk(content_delta="hi", done=True)

        client = ConcreteClient()
        assert isinstance(client, LLMClient)
        resp = client.chat([])
        assert resp.content == "hi"
