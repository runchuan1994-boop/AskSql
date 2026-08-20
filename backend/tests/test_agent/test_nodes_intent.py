"""Tests for agent nodes: intent, probe, clarify."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.agent.state import AgentState, IntentResult, ProbeFinding, ReactThought
from nl2sql.schema import Column, DatasourceSchema, Schema, Table
from nl2sql.llm import ChatResponse, Message, MessageRole
from nl2sql.executor import ExecutionResult, SQLExecutor


# ---------------------------------------------------------------------------
# Mock executor for testing
# ---------------------------------------------------------------------------

class MockExecutor(SQLExecutor):
    """A mock SQL executor that returns canned responses."""

    def __init__(self, datasource_id: str = "ds1") -> None:
        self.datasource_id = datasource_id
        self._responses: dict[str, ExecutionResult] = {}

    def set_response(self, sql: str, result: ExecutionResult) -> None:
        self._responses[sql.strip().lower()] = result

    def execute(self, sql: str, timeout_seconds=None) -> ExecutionResult:
        key = sql.strip().lower()
        if key in self._responses:
            return self._responses[key]
        return ExecutionResult(
            success=False,
            sql=sql,
            error=f"No mock response for: {sql}",
        )

    def test_connection(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_datasource() -> DatasourceSchema:
    """Build a sample datasource with two tables."""
    users = Table(
        name="users",
        description="用户表",
        columns=[
            Column(name="id", type="INT", is_primary_key=True, description="用户ID"),
            Column(name="name", type="VARCHAR(255)", description="用户名"),
            Column(name="email", type="VARCHAR(255)", description="邮箱"),
        ],
    )
    orders = Table(
        name="orders",
        description="订单表",
        columns=[
            Column(name="id", type="INT", is_primary_key=True, description="订单ID"),
            Column(name="user_id", type="INT", is_foreign_key=True,
                   foreign_key_table="users", foreign_key_column="id",
                   description="用户ID"),
            Column(name="amount", type="DECIMAL(10,2)", description="金额"),
        ],
    )
    return DatasourceSchema(
        datasource_id="ds1",
        datasource_name="测试数据源",
        datasource_type="mysql",
        db_schema=Schema(tables=[users, orders]),
    )


@pytest.fixture
def mock_executor() -> MockExecutor:
    return MockExecutor(datasource_id="ds1")


@pytest.fixture
def agent_state(sample_datasource, mock_executor) -> AgentState:
    """Create an AgentState with a mock executor attached."""
    state = AgentState(
        project_id="proj-1",
        datasources=[sample_datasource],
        user_query="统计用户总数",
    )
    state.datasource_executors = {"ds1": mock_executor}
    return state


# ===========================================================================
# need_clarify_conditional
# ===========================================================================

class TestNeedClarifyConditional:
    """Tests for the need_clarify_conditional edge function."""

    def test_returns_ask_clarify_when_questions_exist(self, agent_state):
        """Should return 'ask_clarify' when there are clarification questions."""
        from nl2sql.agent.nodes.clarify import need_clarify_conditional
        agent_state.clarification_questions = ["请确认时间范围"]
        agent_state.awaiting_clarification = True
        assert need_clarify_conditional(agent_state) == "ask_clarify"

    def test_returns_generate_sql_when_no_questions(self, agent_state):
        """Should return 'generate_sql' when no clarification questions."""
        from nl2sql.agent.nodes.clarify import need_clarify_conditional
        agent_state.clarification_questions = []
        agent_state.awaiting_clarification = False
        assert need_clarify_conditional(agent_state) == "generate_sql"

    def test_returns_generate_sql_when_questions_answered(self, agent_state):
        """Should return 'generate_sql' when questions exist but not awaiting."""
        from nl2sql.agent.nodes.clarify import need_clarify_conditional
        agent_state.clarification_questions = ["请确认时间范围"]
        agent_state.awaiting_clarification = False
        assert need_clarify_conditional(agent_state) == "generate_sql"


# ===========================================================================
# intent_analyze_node
# ===========================================================================

class TestIntentAnalyzeNode:
    """Tests for intent_analyze_node."""

    def test_intent_analyze_returns_intent_result(self, agent_state):
        """intent_analyze_node should parse LLM JSON response into IntentResult."""
        from nl2sql.agent.nodes.intent import intent_analyze_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "tables": [{"name": "users", "reason": "用户表"}],
                "filters": [],
                "aggregation": "count",
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.9,
                "analysis": "用户想统计用户总数",
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
            result = intent_analyze_node(agent_state)

        assert "intent" in result
        intent = result["intent"]
        assert isinstance(intent, IntentResult)
        assert intent.confidence == 0.9
        assert intent.aggregation == "count"
        assert len(intent.tables) == 1
        assert intent.tables[0]["name"] == "users"
        assert result["status"] == "thinking"

    def test_intent_analyze_handles_markdown_json(self, agent_state):
        """Should handle JSON wrapped in markdown code blocks."""
        from nl2sql.agent.nodes.intent import intent_analyze_node

        mock_llm = MagicMock()
        json_body = json.dumps({
            "tables": [{"name": "orders", "reason": "订单表"}],
            "filters": [],
            "aggregation": "sum",
            "dimensions": [],
            "ambiguities": ["未指定时间范围"],
            "confidence": 0.7,
            "analysis": "用户想统计订单总金额",
        })
        mock_llm.chat.return_value = ChatResponse(
            content=f"```json\n{json_body}\n```",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
            result = intent_analyze_node(agent_state)

        intent = result["intent"]
        assert intent.aggregation == "sum"
        assert len(intent.ambiguities) == 1
        assert "未指定时间范围" in intent.ambiguities

    def test_intent_analyze_handles_non_json_gracefully(self, agent_state):
        """Should return IntentResult with error info when LLM returns non-JSON."""
        from nl2sql.agent.nodes.intent import intent_analyze_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="我不确定这个问题的意思。",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
            result = intent_analyze_node(agent_state)

        intent = result["intent"]
        assert isinstance(intent, IntentResult)
        assert intent.raw_analysis == "我不确定这个问题的意思。"
        # Should not crash, returns default IntentResult with low confidence
        assert intent.confidence <= 0.1

    def test_intent_analyze_sends_event_when_callback_set(self, agent_state):
        """Should send intent_analysis event when event_callback is provided."""
        from nl2sql.agent.nodes.intent import intent_analyze_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "tables": [],
                "filters": [],
                "aggregation": None,
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.8,
                "analysis": "test",
            }),
            model="test-model",
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
            intent_analyze_node(agent_state)

        event_callback.assert_called_once()
        call_args = event_callback.call_args[0]
        assert call_args[0] == "intent_analysis"


# ===========================================================================
# ask_clarify_node
# ===========================================================================

class TestAskClarifyNode:
    """Tests for ask_clarify_node."""

    def test_ask_clarify_sets_status(self, agent_state):
        """ask_clarify_node should set status to 'clarifying'."""
        from nl2sql.agent.nodes.clarify import ask_clarify_node
        agent_state.clarification_questions = ["请确认时间范围"]
        result = ask_clarify_node(agent_state)
        assert result["status"] == "clarifying"


# ===========================================================================
# clarify_node
# ===========================================================================

class TestClarifyNode:
    """Tests for clarify_node."""

    def test_clarify_node_with_ambiguities_asks_questions(self, agent_state):
        """clarify_node should ask clarification questions when ambiguities remain."""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=["未指定统计的时间范围"],
            confidence=0.6,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps(["请问你想统计哪个时间段的用户数？"]),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert "clarification_questions" in result
        assert len(result["clarification_questions"]) == 1
        assert result["awaiting_clarification"] is True

    def test_clarify_node_no_ambiguities(self, agent_state):
        """clarify_node should set no questions when there are no ambiguities."""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=[],
            confidence=0.9,
        )

        # Even without ambiguities, clarify_node still calls LLM to confirm
        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps([]),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert result["clarification_questions"] == []
        assert result["awaiting_clarification"] is False
