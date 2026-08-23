"""Tests for agent nodes: intent, probe, clarify."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, ANY

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

    def test_intent_analyze_handles_null_datasource_info(self, agent_state):
        """Should treat null datasource_info as empty dict (not crash)."""
        from nl2sql.agent.nodes.intent import intent_analyze_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "tables": [{"name": "loans", "reason": "贷款表"}],
                "filters": [],
                "aggregation": None,
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.8,
                "analysis": "用户想查询最近的贷款情况",
                "action": "query",
                "datasource_info": None,
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
            result = intent_analyze_node(agent_state)

        intent = result["intent"]
        assert isinstance(intent, IntentResult)
        assert intent.action == "query"
        # null should be treated as empty dict, not cause validation error
        assert intent.datasource_info == {}

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

        event_callback.assert_any_call("intent_analysis", ANY)
        # 确认 step_detail 事件也被发送了
        event_names = [call[0][0] for call in event_callback.call_args_list]
        assert "step_detail" in event_names
        assert "intent_analysis" in event_names


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

    def test_clarify_node_with_low_confidence_and_many_ambiguities_asks(self, agent_state):
        """低置信度且有多个歧义时，才触发澄清（新策略：减少澄清次数）。"""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=[
                "不清楚用户说的'活跃'具体指什么业务定义",
                "不确定用哪个表来统计",
            ],
            confidence=0.3,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps(["请问你说的'活跃用户'具体是怎么定义的？"]),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert "clarification_questions" in result
        assert len(result["clarification_questions"]) == 1
        assert result["awaiting_clarification"] is True

    def test_clarify_node_high_confidence_fast_path_no_clarify(self, agent_state):
        """高置信度（>=0.7）时快速跳过澄清，不调用 LLM。"""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=["未指定时间范围"],
            confidence=0.85,
        )

        # 不应该调用 LLM（快速路径）
        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert result["clarification_questions"] == []
        assert result["awaiting_clarification"] is False
        mock_llm.chat.assert_not_called()

    def test_clarify_node_medium_confidence_few_ambiguities_skips(self, agent_state):
        """中等置信度（>=0.5）且少量歧义（<=1）时，跳过澄清（由 query_rewrite 处理）。"""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=["未指定统计的时间范围"],
            confidence=0.6,
        )

        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert result["clarification_questions"] == []
        assert result["awaiting_clarification"] is False
        mock_llm.chat.assert_not_called()

    def test_clarify_node_no_ambiguities(self, agent_state):
        """无歧义且高置信度时快速跳过。"""
        from nl2sql.agent.nodes.clarify import clarify_node

        agent_state.intent = IntentResult(
            ambiguities=[],
            confidence=0.9,
        )

        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm):
            result = clarify_node(agent_state)

        assert result["clarification_questions"] == []
        assert result["awaiting_clarification"] is False
        mock_llm.chat.assert_not_called()


# ===========================================================================
# query_rewrite_node
# ===========================================================================

class TestQueryRewriteNode:
    """Tests for query_rewrite_node."""

    def test_rewrite_high_confidence_no_ambiguities_skips(self, agent_state):
        """高置信度且无歧义时，跳过改写。"""
        from nl2sql.agent.nodes.rewrite import query_rewrite_node

        agent_state.intent = IntentResult(
            ambiguities=[],
            confidence=0.9,
            tables=[{"name": "users", "reason": "用户表"}],
        )
        agent_state.user_query = "统计用户总数"

        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm):
            result = query_rewrite_node(agent_state)

        # 跳过改写，返回空 dict
        assert result == {}
        mock_llm.chat.assert_not_called()

    def test_rewrite_low_confidence_skips(self, agent_state):
        """置信度过低时，跳过改写（交由澄清处理）。"""
        from nl2sql.agent.nodes.rewrite import query_rewrite_node

        agent_state.intent = IntentResult(
            ambiguities=["不知道用户要什么", "不确定用哪个表", "指标也不明确"],
            confidence=0.2,
            tables=[],
        )
        agent_state.user_query = "帮我看看数据"

        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm):
            result = query_rewrite_node(agent_state)

        # 跳过改写
        assert result == {}
        mock_llm.chat.assert_not_called()

    def test_rewrite_medium_confidence_with_ambiguities_rewrites(self, agent_state):
        """中等置信度且有少量歧义时，进行改写。"""
        from nl2sql.agent.nodes.rewrite import query_rewrite_node

        agent_state.intent = IntentResult(
            ambiguities=["未指定时间范围"],
            confidence=0.6,
            tables=[{"name": "users", "reason": "用户表"}],
            assumptions=["假设'最近'指最近 30 天"],
        )
        agent_state.user_query = "最近新增了多少用户"

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "rewritten_query": "统计最近 30 天新增的用户数量",
                "assumptions": [
                    "假设'最近'指最近 30 天",
                    "假设'新增'指 created_at 字段统计",
                ],
                "should_rewrite": True,
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm):
            result = query_rewrite_node(agent_state)

        assert "rewritten_query" in result
        assert "query_assumptions" in result
        assert result["rewritten_query"] == "统计最近 30 天新增的用户数量"
        assert len(result["query_assumptions"]) == 2
        assert "user_query" in result  # user_query 被更新为改写后版本
        assert result["user_query"] == result["rewritten_query"]
        assert "original_query" in result

    def test_rewrite_llm_says_no_rewrite_returns_empty(self, agent_state):
        """LLM 判断不需要改写时，返回空。"""
        from nl2sql.agent.nodes.rewrite import query_rewrite_node

        agent_state.intent = IntentResult(
            ambiguities=["未指定排序方向"],
            confidence=0.6,
            tables=[{"name": "users", "reason": "用户表"}],
        )
        agent_state.user_query = "按注册时间排序的用户列表"

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "rewritten_query": "",
                "assumptions": [],
                "should_rewrite": False,
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm):
            result = query_rewrite_node(agent_state)

        assert result == {}

    def test_rewrite_no_intent_skips(self, agent_state):
        """没有意图结果时，跳过改写。"""
        from nl2sql.agent.nodes.rewrite import query_rewrite_node

        agent_state.intent = None
        agent_state.user_query = "test query"

        mock_llm = MagicMock()

        with patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm):
            result = query_rewrite_node(agent_state)

        assert result == {}
        mock_llm.chat.assert_not_called()
