"""Step detail event utilities for agent nodes.

Provides unified helpers to emit step_detail SSE events from each node.
Also creates Langfuse spans for tracing (when enabled).

Usage:

    from ._step_utils import step_start, step_complete, step_error

    def my_node(state: dict) -> dict:
        start = step_start(state, "my_step", "我的步骤")
        try:
            result = do_work()
            step_complete(state, "my_step", "我的步骤", {"key": "value"}, start)
            return result
        except Exception as e:
            step_error(state, "my_step", "我的步骤", str(e), start)
            raise
"""
from __future__ import annotations

import time
from typing import Any


# Tracing is optional — import lazily to avoid hard dependency
def _get_tracer():
    """Import and return tracer span helpers, or None if tracing unavailable."""
    try:
        from nl2sql.tracing import tracer
        return tracer
    except Exception:
        return None


def _send_event(state: dict | Any, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set.

    Compatible with both dict state (LangGraph runtime) and Pydantic model state (tests).
    """
    if isinstance(state, dict):
        callback = state.get("event_callback")
    else:
        callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def _get_tracing_spans(state: dict | Any) -> dict:
    """Get the _tracing_spans dict from state."""
    if isinstance(state, dict):
        if "_tracing_spans" not in state:
            state["_tracing_spans"] = {}
        return state["_tracing_spans"]
    # Pydantic model state — just use a thread-local / no-op fallback
    return {}


def step_start(state: dict, step: str, name: str) -> float:
    """Emit a step_detail event with status=active and return start time.

    Also creates a Langfuse span (when tracing is enabled and a trace is active).

    Args:
        state: Agent state dict (must have event_callback)
        step: Unique step key (e.g. "intent_analysis")
        name: Chinese display name (e.g. "意图分析")

    Returns:
        Start timestamp (perf_counter) for duration calculation
    """
    _send_event(state, "step_detail", {
        "step": step,
        "name": name,
        "status": "active",
    })

    # Tracing: create span
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            span_ctx = tracer.span(
                name=step,
                metadata={"display_name": name},
            )
            # Use context manager manually (need to store in state for step_complete)
            span_obj = span_ctx.__enter__()
            spans[step] = (span_ctx, span_obj)
        except Exception:
            # Tracing failures should never break the flow
            pass

    return time.perf_counter()


def step_complete(
    state: dict,
    step: str,
    name: str,
    detail: dict[str, Any] | None = None,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=completed.

    Also ends the corresponding Langfuse span.

    Args:
        state: Agent state dict
        step: Unique step key
        name: Chinese display name
        detail: Structured detail dict
        start_time: Start timestamp from step_start() for duration calculation
    """
    payload: dict[str, Any] = {
        "step": step,
        "name": name,
        "status": "completed",
    }
    if start_time is not None:
        payload["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    if detail is not None:
        payload["detail"] = detail
    _send_event(state, "step_detail", payload)

    # Tracing: end span
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            entry = spans.pop(step, None)
            if entry is not None:
                span_ctx, span_obj = entry
                if detail is not None:
                    span_obj.update(metadata={"detail": detail})
                span_ctx.__exit__(None, None, None)
        except Exception:
            pass


def step_error(
    state: dict,
    step: str,
    name: str,
    error_message: str,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=error.

    Also ends the corresponding Langfuse span with error status.

    Args:
        state: Agent state dict
        step: Unique step key
        name: Chinese display name
        error_message: Error description
        start_time: Start timestamp from step_start()
    """
    payload: dict[str, Any] = {
        "step": step,
        "name": name,
        "status": "error",
        "error_message": error_message,
    }
    if start_time is not None:
        payload["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    _send_event(state, "step_detail", payload)

    # Tracing: end span with error
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            entry = spans.pop(step, None)
            if entry is not None:
                span_ctx, span_obj = entry
                span_obj.update(metadata={"error": error_message})
                try:
                    span_ctx.__exit__(Exception, Exception(error_message), None)
                except Exception:
                    pass
        except Exception:
            pass
