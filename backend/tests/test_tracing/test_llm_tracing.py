"""Tests for LLM client tracing integration."""
from __future__ import annotations

import pytest

from nl2sql.llm.base import ChatChunk, ChatResponse, LLMClient
from nl2sql.llm.message import Message, MessageRole
from nl2sql.tracing.langfuse_client import reset_client_for_tests


class _FakeLLMClient(LLMClient):
    """Concrete test double that returns canned responses."""

    model = "fake-model"
    provider = "fake"

    def _chat_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
        return ChatResponse(
            content="Hello from fake LLM",
            model=self.model,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    def _chat_stream_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
        yield ChatChunk(content_delta="Hello", done=False)
        yield ChatChunk(done=True)


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._generations = []
        self._children = []

    def generation(self, **kwargs):
        g = _MockGeneration(kwargs.get("name", "g"))
        g._kwargs = kwargs
        self._generations.append(g)
        return g

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    pass


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self.id = f"gen_{name}"
        self._updates = []
        self._ended = False

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        t._kwargs = kwargs
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    """Enable tracing with a mock Langfuse client."""
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


@pytest.fixture(autouse=True)
def _reset_tracing():
    """Reset tracing client before and after each test for isolation."""
    reset_client_for_tests()
    yield
    reset_client_for_tests()


def test_chat_still_works_without_tracing():
    """When tracing is disabled, chat() works exactly as before."""
    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]
    resp = client.chat(messages)
    assert resp.content == "Hello from fake LLM"
    assert resp.model == "fake-model"
    assert resp.usage == {"input_tokens": 10, "output_tokens": 5}


def test_chat_creates_generation_under_current_span():
    """When a span is active, chat() creates a generation under it."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span

    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]

    with trace(name="t"):
        with span(name="my_step"):
            resp = client.chat(messages, temperature=0.5)

    assert resp.content == "Hello from fake LLM"

    # Trace has span child (not generation directly on trace)
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._generations) == 0
    assert len(trace_obj._children) == 1
    span_obj = trace_obj._children[0]
    assert span_obj.name == "my_step"

    # Generation was created under the span
    assert len(span_obj._generations) == 1
    gen = span_obj._generations[0]
    assert gen._kwargs["model"] == "fake-model"
    assert gen._kwargs["metadata"]["temperature"] == 0.5
    assert gen._kwargs["metadata"]["has_tools"] is False
    # Input is serialized messages
    assert len(gen._kwargs["input"]) == 1
    assert gen._kwargs["input"][0]["content"] == "Hi"
    # Output was set via update
    assert len(gen._updates) == 1
    assert gen._updates[0]["output"] == "Hello from fake LLM"
    assert gen._updates[0]["usage"]["input_tokens"] == 10
    assert gen._updates[0]["usage"]["output_tokens"] == 5


def test_chat_without_trace_is_noop():
    """If no trace/span is active but tracing is enabled, still no-op (no crash)."""
    _enable_with_mock()
    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]

    # No trace active
    resp = client.chat(messages)
    assert resp.content == "Hello from fake LLM"  # still works
