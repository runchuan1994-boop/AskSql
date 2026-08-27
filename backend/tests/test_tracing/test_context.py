"""Tests for tracing context management via contextvars."""
from __future__ import annotations


def test_default_trace_is_none():
    """默认没有活跃 trace。"""
    from nl2sql.tracing.context import get_current_trace
    assert get_current_trace() is None


def test_default_span_is_none():
    """默认没有活跃 span。"""
    from nl2sql.tracing.context import get_current_span
    assert get_current_span() is None


def test_set_and_reset_trace():
    """设置当前 trace 后可以读取，reset 后回到 None。"""
    from nl2sql.tracing.context import set_current_trace, get_current_trace, reset_current_trace

    token = set_current_trace("fake_trace_obj")
    assert get_current_trace() == "fake_trace_obj"

    reset_current_trace(token)
    assert get_current_trace() is None


def test_set_and_reset_span():
    """设置当前 span 后可以读取，reset 后回到 None。"""
    from nl2sql.tracing.context import set_current_span, get_current_span, reset_current_span

    token = set_current_span("fake_span_obj")
    assert get_current_span() == "fake_span_obj"

    reset_current_span(token)
    assert get_current_span() is None


def test_span_stacking():
    """多层 span 嵌套：reset 后应回到父 span。"""
    from nl2sql.tracing.context import set_current_span, get_current_span, reset_current_span

    token1 = set_current_span("parent")
    assert get_current_span() == "parent"

    token2 = set_current_span("child")
    assert get_current_span() == "child"

    reset_current_span(token2)
    assert get_current_span() == "parent"

    reset_current_span(token1)
    assert get_current_span() is None
