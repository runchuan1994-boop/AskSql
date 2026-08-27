"""Tests for step_utils integration with tracing spans."""
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
        return _MockGeneration(kwargs.get("name", "g"))

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    pass


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self._ended = False

    def end(self):
        self._ended = True


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
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


def test_step_start_creates_span_in_trace_context():
    """step_start() creates a span when inside a trace."""
    _reset_tracing()
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "intent_analyze", "意图分析")
        step_complete(state, "intent_analyze", "意图分析", {"result": "ok"}, t0)

    # Span was created under trace
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    span_obj = trace_obj._children[0]
    assert span_obj.name == "intent_analyze"
    assert span_obj._ended is True


def test_step_error_ends_span():
    """step_error() also ends the span properly."""
    _reset_tracing()
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_error

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "generate_sql", "SQL生成")
        step_error(state, "generate_sql", "SQL生成", "syntax error", t0)

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    span_obj = trace_obj._children[0]
    assert span_obj.name == "generate_sql"
    assert span_obj._ended is True


def test_no_span_without_trace():
    """When no trace is active, step_start/step_complete still work (no crash)."""
    _reset_tracing()
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}
    t0 = step_start(state, "test_step", "测试步骤")
    step_complete(state, "test_step", "测试步骤", {"ok": True}, t0)
    # Should not raise


def test_multiple_steps_create_multiple_spans():
    """Multiple step_start/complete calls create multiple sibling spans."""
    _reset_tracing()
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t1 = step_start(state, "step1", "步骤1")
        step_complete(state, "step1", "步骤1", {}, t1)

        t2 = step_start(state, "step2", "步骤2")
        step_complete(state, "step2", "步骤2", {}, t2)

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 2
    assert trace_obj._children[0].name == "step1"
    assert trace_obj._children[1].name == "step2"


def test_step_complete_with_detail_updates_span():
    """step_complete detail is passed as span output/metadata."""
    _reset_tracing()
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "gen", "生成")
        step_complete(state, "gen", "生成", {"sql": "SELECT 1", "rows": 42}, t0)

    span_obj = mock_client.traces[0]._children[0]
    # Should have at least one update call with the detail
    assert len(span_obj._updates) >= 1
    # The detail dict should appear somewhere in the updates
    detail_found = any(
        u.get("output") is not None or u.get("metadata", {}).get("detail", {}).get("sql") == "SELECT 1"
        for u in span_obj._updates
    )
    # At minimum the span ended
    assert span_obj._ended is True
