"""Tests for tracer in no-op mode (Langfuse disabled)."""
from __future__ import annotations

from unittest.mock import patch


def _disable_tracing():
    """Patch Settings to disable tracing and reset singleton."""
    import nl2sql.tracing.langfuse_client as lc
    lc._client = None
    lc._initialized = False

    mock_settings = type(
        "Settings",
        (),
        {
            "langfuse_enabled": False,
            "langfuse_public_key": "",
            "langfuse_secret_key": "",
            "langfuse_host": "http://localhost:3030",
        },
    )()
    return patch("nl2sql.tracing.langfuse_client.Settings", return_value=mock_settings)


def test_trace_context_noop():
    """trace() in no-op mode yields a context object with update method."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import trace
        with trace(name="test_trace") as ctx:
            assert hasattr(ctx, "update")
            assert hasattr(ctx, "id")
            assert ctx.id is None
            ctx.update(output="hello")  # should not raise


def test_span_context_noop():
    """span() in no-op mode yields a context object."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import span
        with span(name="test_span") as ctx:
            assert hasattr(ctx, "update")
            ctx.update(output="result", metadata={"key": "val"})  # should not raise


def test_generation_context_noop():
    """generation() in no-op mode yields a context object."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import generation
        with generation(name="test_gen", model="gpt-4") as ctx:
            assert hasattr(ctx, "update")
            ctx.update(output="hello", usage={"input_tokens": 10, "output_tokens": 5})


def test_nested_noop():
    """多层嵌套在 no-op 模式下不报错。"""
    with _disable_tracing():
        from nl2sql.tracing.tracer import trace, span, generation
        with trace(name="t"):
            with span(name="s1"):
                with generation(name="g1", model="m") as gen:
                    gen.update(output="x")
            with span(name="s2"):
                pass
        # 全部结束后上下文应该回到 None
        from nl2sql.tracing.context import get_current_trace, get_current_span
        assert get_current_trace() is None
        assert get_current_span() is None
