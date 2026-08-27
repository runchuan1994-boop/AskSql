"""Tests for tracer with a mock Langfuse client (verifies nesting and calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


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
        gen = _MockGeneration(kwargs.get("name", "gen"))
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    def __init__(self, name):
        super().__init__(name)
        self.id = f"trace_{name}"
        self._scores = []

    def score(self, **kwargs):
        self._scores.append(kwargs)


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self.id = f"gen_{name}"
        self._ended = False
        self._updates = []

    def update(self, **kwargs):
        self._updates.append(kwargs)

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
    """Enable tracing with a mock Langfuse client."""
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def test_trace_creates_trace_on_client():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace

    with trace(name="my_trace", user_id="u1", session_id="s1") as t:
        assert t.id == "trace_my_trace"

    assert len(mock_client.traces) == 1
    assert mock_client.traces[0].name == "my_trace"


def test_trace_sets_contextvar():
    _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.tracing.context import get_current_trace

    assert get_current_trace() is None
    with trace(name="t"):
        assert get_current_trace() is not None
    assert get_current_trace() is None


def test_span_nested_under_trace():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span

    with trace(name="t"):
        with span(name="s1") as s:
            assert s.id == "span_s1"

    assert len(mock_client.traces) == 1
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    assert trace_obj._children[0].name == "s1"
    assert trace_obj._children[0]._ended is True


def test_generation_nested_under_span():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span, generation

    with trace(name="t"):
        with span(name="s"):
            with generation(name="g", model="gpt-4") as g:
                g.update(output="hello", usage={"input_tokens": 10, "output_tokens": 5})

    trace_obj = mock_client.traces[0]
    span_obj = trace_obj._children[0]
    gen_obj = span_obj._children[0]
    assert gen_obj.name == "g"
    assert gen_obj._ended is True
    # Check that update was called with normalized usage
    assert len(gen_obj._updates) == 1
    update = gen_obj._updates[0]
    assert update["usage"]["input_tokens"] == 10
    assert update["usage"]["output_tokens"] == 5


def test_span_stacking_two_levels():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span
    from nl2sql.tracing.context import get_current_span

    with trace(name="t"):
        with span(name="parent") as p:
            assert get_current_span().name == "parent"
            with span(name="child") as c:
                assert get_current_span().name == "child"
            assert get_current_span().name == "parent"

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    parent = trace_obj._children[0]
    assert parent.name == "parent"
    assert len(parent._children) == 1
    assert parent._children[0].name == "child"


def test_openai_usage_normalized():
    """OpenAI returns prompt_tokens/completion_tokens; should be normalized."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span, generation

    with trace(name="t"):
        with span(name="s"):
            with generation(name="g") as g:
                g.update(usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                })

    gen_obj = mock_client.traces[0]._children[0]._children[0]
    update = gen_obj._updates[0]
    assert update["usage"]["input_tokens"] == 100
    assert update["usage"]["output_tokens"] == 50
    assert update["usage"]["total_tokens"] == 150
