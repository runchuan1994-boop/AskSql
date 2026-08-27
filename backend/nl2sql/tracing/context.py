"""Tracing context management using contextvars.

Provides thread-safe (and async-safe) storage for the currently active
trace and span. LLM client layer reads from here to auto-nest
generations under the current span.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_current_trace: ContextVar[Any] = ContextVar("current_trace", default=None)
_current_span: ContextVar[Any] = ContextVar("current_span", default=None)


def get_current_trace() -> Any:
    """Get the currently active trace object, or None."""
    return _current_trace.get()


def get_current_span() -> Any:
    """Get the currently active span object, or None."""
    return _current_span.get()


def set_current_trace(trace: Any) -> Any:
    """Set the current trace. Returns a token for reset."""
    return _current_trace.set(trace)


def set_current_span(span: Any) -> Any:
    """Set the current span. Returns a token for reset."""
    return _current_span.set(span)


def reset_current_trace(token: Any) -> None:
    """Reset trace to previous value using token from set_current_trace."""
    _current_trace.reset(token)


def reset_current_span(token: Any) -> None:
    """Reset span to previous value using token from set_current_span."""
    _current_span.reset(token)
