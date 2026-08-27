"""Tests for DispatcherAgent tracing integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        gen = MagicMock()
        gen.end = MagicMock()
        gen._updates = []
        def update(**kw):
            gen._updates.append(kw)
        gen.update = update
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    pass


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
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def _reset_tracing():
    from nl2sql.tracing.langfuse_client import reset_client_for_tests
    reset_client_for_tests()


def _make_fake_dispatcher(intent_result="chitchat"):
    """Create a DispatcherAgent with mocked LLM and sub-agents."""
    from nl2sql.agent.dispatcher import DispatcherAgent

    dispatcher = DispatcherAgent(
        project_id="test_proj",
        datasources=[],
        executors={},
    )

    # Mock _classify_intent to return a fixed intent
    from nl2sql.agent.dispatcher import DispatchResult
    dispatcher._classify_intent = lambda q, h=None: DispatchResult(
        intent=intent_result, confidence=0.9, reasoning="test"
    )

    # Mock chitchat (used as the simplest path)
    dispatcher._run_chitchat = lambda q: {
        "answer": "hi there",
        "status": "done",
        "intent": "chitchat",
    }

    return dispatcher


def test_dispatcher_creates_span_in_trace():
    """Dispatcher.run() creates a 'dispatcher' span inside an active trace."""
    _reset_tracing()
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace

    dispatcher = _make_fake_dispatcher("chitchat")

    with trace(name="chat_turn"):
        result = dispatcher.run("hello")

    assert result["intent"] == "chitchat"
    assert result["answer"] == "hi there"

    # Check trace -> dispatcher span nesting
    trace_obj = mock_client.traces[0]
    # Find the dispatcher span (should be a direct child of trace)
    disp_spans = [c for c in trace_obj._children if isinstance(c, _MockSpan) and c.name == "dispatcher"]
    assert len(disp_spans) == 1, f"Expected 1 dispatcher span, got {len(disp_spans)}"
    assert disp_spans[0]._ended is True


def test_dispatcher_works_without_trace():
    """Dispatcher.run() works normally when no trace is active."""
    _reset_tracing()
    dispatcher = _make_fake_dispatcher("chitchat")
    result = dispatcher.run("hello")
    assert result["status"] == "done"
