"""Core tracer: trace / span / generation context managers.

Provides a clean API that business code uses. Under the hood, delegates
to the Langfuse SDK when enabled, or is a complete no-op when disabled.

Design principles:
- Callers never import langfuse directly
- All three context managers have the same shape: __enter__ returns a
  context object with .update() and .id, __exit__ handles cleanup
- Context variables (trace/span) are automatically set and reset
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from . import context as ctx
from .langfuse_client import get_langfuse


# ---------------------------------------------------------------------------
# Context objects (uniform API for both real and no-op modes)
# ---------------------------------------------------------------------------

class _NoopContext:
    """Placeholder context returned when tracing is disabled.

    Has the same API as real contexts but does nothing.
    """

    id: None = None

    def update(self, **kwargs: Any) -> None:
        pass

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        pass


class _TraceContext:
    """Wraps a Langfuse trace object."""

    def __init__(self, trace: Any) -> None:
        self._trace = trace

    @property
    def id(self) -> str:
        return self._trace.id

    def update(self, output: Any = None, metadata: dict | None = None, **_: Any) -> None:
        if output is not None:
            self._trace.update(output=output)
        if metadata is not None:
            self._trace.update(metadata=metadata)

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        kwargs: dict[str, Any] = {"name": name, "value": value}
        if comment is not None:
            kwargs["comment"] = comment
        self._trace.score(**kwargs)


class _SpanContext:
    """Wraps a Langfuse span object."""

    def __init__(self, span: Any) -> None:
        self._span = span

    @property
    def id(self) -> str:
        return self._span.id

    def update(self, output: Any = None, metadata: dict | None = None, **_: Any) -> None:
        if output is not None:
            self._span.update(output=output)
        if metadata is not None:
            self._span.update(metadata=metadata)


class _GenerationContext:
    """Wraps a Langfuse generation object."""

    def __init__(self, generation: Any) -> None:
        self._generation = generation

    @property
    def id(self) -> str:
        return self._generation.id

    def update(
        self,
        output: Any = None,
        usage: dict | None = None,
        model: str | None = None,
        tool_calls: list | None = None,
        metadata: dict | None = None,
        **_: Any,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if output is not None:
            kwargs["output"] = output
        if usage is not None:
            # Normalize usage keys for Langfuse (expects input_tokens / output_tokens / total_tokens)
            langfuse_usage: dict[str, int] = {}
            if "input_tokens" in usage:
                langfuse_usage["input_tokens"] = usage["input_tokens"]
            elif "prompt_tokens" in usage:
                langfuse_usage["input_tokens"] = usage["prompt_tokens"]
            if "output_tokens" in usage:
                langfuse_usage["output_tokens"] = usage["output_tokens"]
            elif "completion_tokens" in usage:
                langfuse_usage["output_tokens"] = usage["completion_tokens"]
            if "total_tokens" in usage:
                langfuse_usage["total_tokens"] = usage["total_tokens"]
            if langfuse_usage:
                kwargs["usage"] = langfuse_usage
        if model is not None:
            kwargs["model"] = model
        if tool_calls is not None:
            kwargs["metadata"] = {**(kwargs.get("metadata", {})), "tool_calls": tool_calls}
        if metadata is not None:
            existing = kwargs.get("metadata", {})
            existing.update(metadata)
            kwargs["metadata"] = existing
        if kwargs:
            self._generation.update(**kwargs)


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------

@contextmanager
def trace(
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
    input: Any = None,
) -> Iterator[_TraceContext | _NoopContext]:
    """Create a trace (top-level unit of work).

    If tracing is disabled, yields a no-op context.
    Automatically sets current_trace contextvar and restores it on exit.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if user_id is not None:
        kwargs["user_id"] = user_id
    if session_id is not None:
        kwargs["session_id"] = session_id
    if metadata is not None:
        kwargs["metadata"] = metadata
    if input is not None:
        kwargs["input"] = input

    trace_obj = client.trace(**kwargs)
    trace_ctx = _TraceContext(trace_obj)
    token = ctx.set_current_trace(trace_obj)
    try:
        yield trace_ctx
    finally:
        ctx.reset_current_trace(token)


@contextmanager
def span(
    name: str,
    metadata: dict | None = None,
    input: Any = None,
) -> Iterator[_SpanContext | _NoopContext]:
    """Create a span, nested under the current trace and parent span.

    If tracing is disabled or no trace is active, yields a no-op context.
    Automatically sets current_span contextvar and restores it on exit.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    parent = ctx.get_current_span() or ctx.get_current_trace()
    if parent is None:
        # No active trace -> can't create a span. No-op.
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if metadata is not None:
        kwargs["metadata"] = metadata
    if input is not None:
        kwargs["input"] = input

    span_obj = parent.span(**kwargs)
    span_ctx = _SpanContext(span_obj)
    token = ctx.set_current_span(span_obj)
    try:
        yield span_ctx
    finally:
        span_obj.end()
        ctx.reset_current_span(token)


@contextmanager
def generation(
    name: str,
    model: str | None = None,
    input: Any = None,
    metadata: dict | None = None,
) -> Iterator[_GenerationContext | _NoopContext]:
    """Create a generation (LLM call), nested under the current span.

    If tracing is disabled or no span/trace is active, yields a no-op context.
    Does NOT modify the current_span contextvar — generations are leaves.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    parent = ctx.get_current_span() or ctx.get_current_trace()
    if parent is None:
        # No active trace -> no-op
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if model is not None:
        kwargs["model"] = model
    if input is not None:
        kwargs["input"] = input
    if metadata is not None:
        kwargs["metadata"] = metadata

    gen_obj = parent.generation(**kwargs)
    gen_ctx = _GenerationContext(gen_obj)
    try:
        yield gen_ctx
    finally:
        gen_obj.end()


def flush() -> None:
    """Flush pending events to Langfuse. No-op if disabled."""
    client = get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
