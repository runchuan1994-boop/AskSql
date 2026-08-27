"""Tests for chat_service trace integration.

These tests verify that the trace is properly created around chat runs.
We mock the dispatcher and DB to isolate tracing behavior.
"""
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
        gen.update = lambda **kw: gen._updates.append(kw)
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    def __init__(self, name):
        super().__init__(name)
        self._kwargs = {}
        self._scores = []

    def score(self, **kwargs):
        self._scores.append(kwargs)


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


def test_trace_created_with_correct_metadata():
    """When tracing is enabled, chat_service creates a trace with proper metadata."""
    _reset_tracing()
    mock_client = _enable_with_mock()

    # Mock all the heavy dependencies
    with patch("app.services.chat_service.session_service") as mock_sess, \
         patch("app.services.chat_service._build_dispatcher_sync") as mock_build, \
         patch("app.services.chat_service._load_history_messages_sync") as mock_hist, \
         patch("app.services.chat_service._start_async_correction_detection") as mock_corr, \
         patch("app.services.chat_service.log_generation") as mock_log, \
         patch("app.services.chat_service.result_cache") as mock_cache, \
         patch("app.services.chat_service.get_connection") as mock_db, \
         patch("app.services.chat_service.get_pending_confirmations") as mock_pending, \
         patch("app.services.chat_service.confirm_pending_memories") as mock_confirm:

        mock_sess.get_session.return_value = {
            "id": "sess_123",
            "project_id": "proj_123",
            "user_id": "user_456",
        }
        mock_sess.add_message.return_value = {"id": "msg_789"}
        mock_sess.update_session_title_from_query.return_value = None

        mock_dispatcher = MagicMock()
        mock_dispatcher.run.return_value = {
            "answer": "Here is your answer",
            "status": "done",
            "sql": "SELECT 1",
            "intent": "query",
            "intent_type": "query",
            "iteration": 1,
            "execution_result": None,
            "react_thoughts": [],
        }
        mock_build.return_value = mock_dispatcher

        mock_hist.return_value = []
        mock_pending.return_value = []

        import asyncio
        loop = asyncio.new_event_loop()

        from app.services.chat_service import _run_chat_sync
        _run_chat_sync("sess_123", "What is the total sales?", loop, "ds_123")

        # Verify a trace was created
        assert len(mock_client.traces) >= 1, "Expected at least one trace"
        trace_obj = mock_client.traces[0]
        assert trace_obj._kwargs["name"] == "chat_turn"
        assert trace_obj._kwargs.get("session_id") == "sess_123"
        # Input should be the user query
        assert trace_obj._kwargs.get("input") == "What is the total sales?"
        # Metadata should contain datasource info
        meta = trace_obj._kwargs.get("metadata", {})
        assert meta.get("datasource_id") == "ds_123"

        loop.close()
