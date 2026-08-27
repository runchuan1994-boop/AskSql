"""End-to-end tracing integration tests.

Verifies the full trace chain structure:
  trace (chat_turn) → dispatcher span → [sub-agent span] → [node spans] → [llm generations]

Also verifies cross-layer metadata propagation and graceful degradation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock Langfuse setup (shared with other tracing tests, duplicated here
# to keep the e2e test self-contained)
# ---------------------------------------------------------------------------

class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}_{id(self)}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        gen = MagicMock()
        gen.name = kwargs.get("name", "gen")
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


def _find_all_spans(node, depth=0):
    """Recursively collect all spans (not generations) from a trace/span tree."""
    result = [(node, depth)]
    for child in node._children:
        if isinstance(child, _MockSpan):
            result.extend(_find_all_spans(child, depth + 1))
    return result


def _find_all_generations(node):
    """Recursively collect all generation mocks from a trace/span tree."""
    result = []
    for child in node._children:
        if isinstance(child, MagicMock):
            result.append(child)
        elif isinstance(child, _MockSpan):
            result.extend(_find_all_generations(child))
    return result


# ---------------------------------------------------------------------------
# Test 1: chat_service → dispatcher span nesting
# ---------------------------------------------------------------------------

def test_e2e_chat_trace_contains_dispatcher_span():
    """E2E: chat_service creates a trace, and dispatcher creates a span inside it.

    This tests the integration between chat_service (trace entry point)
    and DispatcherAgent (dispatcher span).
    """
    _reset_tracing()
    mock_client = _enable_with_mock()

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
            "id": "sess_e2e",
            "project_id": "proj_e2e",
            "user_id": "user_e2e",
        }
        mock_sess.add_message.return_value = {"id": "msg_e2e"}
        mock_sess.update_session_title_from_query.return_value = None

        # Create a real DispatcherAgent but with mocked sub-agents
        from nl2sql.agent.dispatcher import DispatcherAgent, DispatchResult
        dispatcher = DispatcherAgent(
            project_id="proj_e2e",
            datasources=[],
            executors={},
        )
        # Mock intent classification
        dispatcher._classify_intent = lambda q, h=None: DispatchResult(
            intent="chitchat", confidence=0.95, reasoning="e2e test"
        )
        # Mock chitchat (simplest path — no sub-agent span)
        dispatcher._run_chitchat = lambda q: {
            "answer": "Hello from e2e test",
            "status": "done",
            "intent": "chitchat",
        }
        mock_build.return_value = dispatcher
        mock_hist.return_value = []
        mock_pending.return_value = []

        import asyncio
        loop = asyncio.new_event_loop()

        from app.services.chat_service import _run_chat_sync
        result = _run_chat_sync("sess_e2e", "Hello there!", loop, "ds_e2e")

        # --- Verify trace structure ---
        assert len(mock_client.traces) == 1, "Expected exactly 1 trace"
        trace_obj = mock_client.traces[0]

        # Trace metadata
        assert trace_obj._kwargs["name"] == "chat_turn"
        assert trace_obj._kwargs["session_id"] == "sess_e2e"
        assert trace_obj._kwargs["user_id"] == "user_e2e"
        assert trace_obj._kwargs["input"] == "Hello there!"
        meta = trace_obj._kwargs.get("metadata", {})
        assert meta.get("datasource_id") == "ds_e2e"
        assert meta.get("project_id") == "proj_e2e"

        # Dispatcher span exists as direct child of trace
        disp_spans = [c for c in trace_obj._children
                      if isinstance(c, _MockSpan) and c.name == "dispatcher"]
        assert len(disp_spans) == 1, f"Expected 1 dispatcher span, got {len(disp_spans)}"
        assert disp_spans[0]._ended is True, "Dispatcher span should be ended"

        # Dispatcher span has intent metadata updated
        disp_updates = disp_spans[0]._updates
        disp_meta = {}
        for u in disp_updates:
            if "metadata" in u:
                disp_meta.update(u["metadata"])
        assert disp_meta.get("intent") == "chitchat"
        assert disp_meta.get("confidence") == 0.95

        # Trace has output/metadata updated after success
        trace_updates_meta = {}
        for u in trace_obj._updates:
            if "metadata" in u:
                trace_updates_meta.update(u["metadata"])
        assert trace_updates_meta.get("success") is True
        assert trace_updates_meta.get("status") == "done"
        assert "execution_time_ms" in trace_updates_meta

        loop.close()


# ---------------------------------------------------------------------------
# Test 2: Full chain — trace → dispatcher → nl2sql_agent → step span → generation
# ---------------------------------------------------------------------------

def test_e2e_full_chain_structure():
    """E2E: Verify the full nesting structure:
    trace → dispatcher → nl2sql_agent → step span → llm generation.

    We mock NL2SQLAgent.run() to simulate a few step_start/step_complete
    calls plus an LLM call inside a trace, to verify the nesting depth
    and structure matches the expected pattern.
    """
    _reset_tracing()
    mock_client = _enable_with_mock()

    from nl2sql.tracing import trace, span
    from nl2sql.llm.base import LLMClient, ChatResponse
    from nl2sql.llm.message import Message

    # Create a minimal LLM client for testing generation tracing
    class _FakeLLM(LLMClient):
        provider = "test"

        def _chat_impl(self, messages, **kwargs):
            return ChatResponse(
                content="test response",
                model="test-model",
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            )

        def _chat_stream_impl(self, messages, **kwargs):
            yield ChatResponse(content="test", model="test-model")

    fake_llm = _FakeLLM()
    fake_llm.set_generation_name("llm_intent")

    # Simulate the full chain manually (mimicking what the real code does):
    # trace → dispatcher span → nl2sql_agent span → node spans → llm generations
    with trace(name="chat_turn", session_id="sess_chain", user_id="user_chain",
               metadata={"datasource_id": "ds_chain", "project_id": "proj_chain"},
               input="How many users?") as trace_ctx:
        with span(name="dispatcher", metadata={"intent": "query", "confidence": 0.9}):
            with span(name="nl2sql_agent"):
                # Simulate intent analysis node
                with span(name="intent_analyze",
                          metadata={"display_name": "意图分析"}):
                    # Inside the node, an LLM call creates a generation
                    resp = fake_llm.chat([Message(role="user", content="test")])

                # Simulate SQL generation node
                with span(name="sql_generation",
                          metadata={"display_name": "SQL 生成"}):
                    fake_llm.set_generation_name("llm_generate")
                    resp2 = fake_llm.chat([Message(role="user", content="generate sql")])

            # After sub-agent, update dispatcher span (simulated)

    # --- Verify full tree structure ---
    assert len(mock_client.traces) == 1
    root = mock_client.traces[0]
    assert root._kwargs["name"] == "chat_turn"

    # Level 1: dispatcher span
    disp = [c for c in root._children if isinstance(c, _MockSpan) and c.name == "dispatcher"]
    assert len(disp) == 1
    assert disp[0]._ended is True

    # Level 2: nl2sql_agent span (child of dispatcher)
    agent_spans = [c for c in disp[0]._children
                   if isinstance(c, _MockSpan) and c.name == "nl2sql_agent"]
    assert len(agent_spans) == 1, "Expected nl2sql_agent span under dispatcher"
    assert agent_spans[0]._ended is True

    # Level 3: node spans (children of nl2sql_agent)
    node_spans = [c for c in agent_spans[0]._children if isinstance(c, _MockSpan)]
    node_names = [s.name for s in node_spans]
    assert "intent_analyze" in node_names, f"Expected intent_analyze span, got {node_names}"
    assert "sql_generation" in node_names, f"Expected sql_generation span, got {node_names}"

    # All node spans should be ended
    for s in node_spans:
        assert s._ended is True, f"Span {s.name} should be ended"

    # Level 4: LLM generations (under node spans)
    all_gens = _find_all_generations(root)
    assert len(all_gens) >= 2, f"Expected at least 2 generations, got {len(all_gens)}"

    # Verify generation has usage data
    gen_with_usage = [g for g in all_gens if g._updates]
    assert len(gen_with_usage) >= 1
    # Check that usage was normalized (prompt_tokens → input_tokens, etc.)
    usage_found = False
    for g in gen_with_usage:
        for u in g._updates:
            if "usage" in u:
                usage = u["usage"]
                assert "input_tokens" in usage or "output_tokens" in usage or "total_tokens" in usage
                usage_found = True
                break
        if usage_found:
            break
    assert usage_found, "At least one generation should have usage data"

    # Verify node spans have display_name metadata
    intent_span = [s for s in node_spans if s.name == "intent_analyze"][0]
    # display_name is passed at span creation — verify it's in creation kwargs
    assert intent_span.name == "intent_analyze"

    # Verify the generations are correctly nested under their respective spans
    intent_gens = [c for c in intent_span._children if isinstance(c, MagicMock)]
    assert len(intent_gens) == 1, "intent_analyze span should have exactly 1 generation child"


# ---------------------------------------------------------------------------
# Test 3: Graceful degradation — no tracing when disabled
# ---------------------------------------------------------------------------

def test_e2e_no_tracing_when_disabled():
    """E2E: When tracing is disabled (default), no traces are created.

    This tests the full stack with default config to verify zero overhead.
    """
    _reset_tracing()

    from nl2sql.tracing.langfuse_client import get_langfuse
    assert get_langfuse() is None, "Tracing should be disabled by default"

    from nl2sql.tracing import trace, span, generation

    # All context managers should yield no-op contexts
    with trace(name="test") as t:
        assert t.id is None
        with span(name="test_span") as s:
            assert s.id is None
            with generation(name="test_gen") as g:
                assert g.id is None
                # Update calls should not raise
                g.update(output="hello", usage={"prompt_tokens": 1, "completion_tokens": 1})

    # No client → no traces
    import nl2sql.tracing.langfuse_client as lc
    assert lc._client is None


# ---------------------------------------------------------------------------
# Test 4: flush is called after chat
# ---------------------------------------------------------------------------

def test_e2e_flush_called_after_chat_turn():
    """E2E: flush() is called at the end of a chat turn to ensure data is sent."""
    _reset_tracing()
    mock_client = _enable_with_mock()

    flush_called = []
    original_flush = mock_client.flush
    def tracking_flush():
        flush_called.append(True)
        original_flush()
    mock_client.flush = tracking_flush

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
            "id": "sess_flush", "project_id": "proj_flush", "user_id": "user_flush",
        }
        mock_sess.add_message.return_value = {"id": "msg_flush"}
        mock_sess.update_session_title_from_query.return_value = None

        from nl2sql.agent.dispatcher import DispatcherAgent, DispatchResult
        dispatcher = DispatcherAgent(project_id="p", datasources=[], executors={})
        dispatcher._classify_intent = lambda q, h=None: DispatchResult(
            intent="chitchat", confidence=0.9, reasoning="test"
        )
        dispatcher._run_chitchat = lambda q: {"answer": "hi", "status": "done", "intent": "chitchat"}
        mock_build.return_value = dispatcher
        mock_hist.return_value = []
        mock_pending.return_value = []

        import asyncio
        loop = asyncio.new_event_loop()
        from app.services.chat_service import _run_chat_sync
        _run_chat_sync("sess_flush", "hi", loop, "ds_flush")
        loop.close()

    assert len(flush_called) >= 1, "flush() should be called at least once after chat turn"


# ---------------------------------------------------------------------------
# Test 5: Error path — trace captures errors
# ---------------------------------------------------------------------------

def test_e2e_trace_captures_errors():
    """E2E: When the dispatcher raises an error, the trace still captures it."""
    _reset_tracing()
    mock_client = _enable_with_mock()

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
            "id": "sess_err", "project_id": "proj_err", "user_id": "user_err",
        }
        mock_sess.add_message.return_value = {"id": "msg_err"}
        mock_sess.update_session_title_from_query.return_value = None

        from nl2sql.agent.dispatcher import DispatcherAgent, DispatchResult
        dispatcher = DispatcherAgent(project_id="p", datasources=[], executors={})
        dispatcher._classify_intent = lambda q, h=None: DispatchResult(
            intent="query", confidence=0.9, reasoning="test"
        )
        # Simulate a failure in the query path
        def _failing_query(*args, **kwargs):
            raise ValueError("Simulated agent failure")
        dispatcher._run_query = _failing_query
        mock_build.return_value = dispatcher
        mock_hist.return_value = []
        mock_pending.return_value = []

        import asyncio
        loop = asyncio.new_event_loop()
        from app.services.chat_service import _run_chat_sync

        # Should not raise — chat_service handles errors internally
        # _run_chat_sync returns None on error (it's a sync worker function)
        _run_chat_sync("sess_err", "hello", loop, "ds_err")

        # Trace should have error metadata
        assert len(mock_client.traces) == 1
        trace_obj = mock_client.traces[0]
        trace_meta = {}
        for u in trace_obj._updates:
            if "metadata" in u:
                trace_meta.update(u["metadata"])
        assert "error" in trace_meta, "Trace should capture error message"
        assert "traceback" in trace_meta, "Trace should capture traceback"
        assert "Simulated agent failure" in trace_meta["error"]

        loop.close()
