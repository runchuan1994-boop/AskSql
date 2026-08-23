"""Step detail event utilities for agent nodes.

Provides unified helpers to emit step_detail SSE events from each node.
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


def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def step_start(state: dict, step: str, name: str) -> float:
    """Emit a step_detail event with status=active and return start time.

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
    return time.perf_counter()


def step_complete(
    state: dict,
    step: str,
    name: str,
    detail: dict[str, Any] | None = None,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=completed.

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


def step_error(
    state: dict,
    step: str,
    name: str,
    error_message: str,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=error.

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
