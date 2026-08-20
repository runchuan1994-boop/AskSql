"""Tests for agent ReAct nodes: generate, execute, reflect, summarize."""
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
    state = AgentState(
        project_id="proj-1",
        datasources=[sample_datasource],
        user_query="统计用户总数",
    )
    state.datasource_executors = {"ds1": mock_executor}
    state.intent = IntentResult(
        tables=[{"name": "users", "reason": "用户表"}],
        aggregation="count",
        confidence=0.9,
    )
    return state


# ===========================================================================
# extract_sql_from_text
# ===========================================================================

class TestExtractSqlFromText:
    """Tests for the SQL extraction helper."""

    def test_extract_sql_plain_text(self):
        """Should return plain SQL text as-is."""
        from nl2sql.agent.nodes.generate import extract_sql_from_text
        sql = "SELECT COUNT(*) FROM users"
        assert extract_sql_from_text(sql) == sql

    def test_extract_sql_sql_code_block(self):
        """Should extract SQL from ```sql ... ``` block."""
        from nl2sql.agent.nodes.generate import extract_sql_from_text
        sql = "SELECT COUNT(*) FROM users"
        text = f"```sql\n{sql}\n```"
        assert extract_sql_from_text(text) == sql

    def test_extract_sql_generic_code_block(self):
        """Should extract SQL from ``` ... ``` block without language tag."""
        from nl2sql.agent.nodes.generate import extract_sql_from_text
        sql = "SELECT * FROM orders"
        text = f"```\n{sql}\n```"
        assert extract_sql_from_text(text) == sql

    def test_extract_sql_with_explanation_text(self):
        """Should extract SQL from code block surrounded by explanation text."""
        from nl2sql.agent.nodes.generate import extract_sql_from_text
        sql = "SELECT COUNT(*) AS total FROM users"
        text = f"这是生成的 SQL：\n\n```sql\n{sql}\n```\n\n希望对你有帮助。"
        assert extract_sql_from_text(text) == sql

    def test_extract_sql_strips_whitespace(self):
        """Should strip leading/trailing whitespace from extracted SQL."""
        from nl2sql.agent.nodes.generate import extract_sql_from_text
        text = "```sql\n  SELECT 1  \n```"
        assert extract_sql_from_text(text) == "SELECT 1"


# ===========================================================================
# generate_sql_node
# ===========================================================================

class TestGenerateSqlNode:
    """Tests for generate_sql_node."""

    def test_generate_sql_returns_sql(self, agent_state):
        """generate_sql_node should extract and return SQL from LLM response."""
        from nl2sql.agent.nodes.generate import generate_sql_node

        mock_llm = MagicMock()
        sql = "SELECT COUNT(*) AS total FROM users"
        mock_llm.chat.return_value = ChatResponse(
            content=f"```sql\n{sql}\n```",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm):
            result = generate_sql_node(agent_state)

        assert result["sql"] == sql
        assert result["status"] == "thinking"

    def test_generate_sql_uses_intent_tables(self, agent_state):
        """generate_sql_node should include intent tables in schema context."""
        from nl2sql.agent.nodes.generate import generate_sql_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="```sql\nSELECT COUNT(*) FROM users\n```",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm):
            generate_sql_node(agent_state)

        # Check that the LLM was called with messages
        call_args = mock_llm.chat.call_args[0][0]
        # The user message should contain table info
        user_msg = [m for m in call_args if m.role == MessageRole.USER][0].content
        assert "users" in user_msg

    def test_generate_sql_sends_event(self, agent_state):
        """generate_sql_node should send sql_generated event."""
        from nl2sql.agent.nodes.generate import generate_sql_node

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="```sql\nSELECT 1\n```",
            model="test-model",
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm):
            generate_sql_node(agent_state)

        event_types = [call[0][0] for call in event_callback.call_args_list]
        assert "sql_generated" in event_types


# ===========================================================================
# execute_sql_node
# ===========================================================================

class TestExecuteSqlNode:
    """Tests for execute_sql_node."""

    def test_execute_sql_success(self, agent_state, mock_executor):
        """execute_sql_node should execute SQL and return result."""
        from nl2sql.agent.nodes.execute import execute_sql_node

        sql = "SELECT COUNT(*) AS total FROM users"
        agent_state.sql = sql
        mock_executor.set_response(
            sql,
            ExecutionResult(
                success=True,
                sql=sql,
                columns=["total"],
                rows=[(100,)],
                row_count=1,
                duration_ms=1.0,
            ),
        )

        result = execute_sql_node(agent_state)

        assert result["execution_result"].success is True
        assert result["execution_result"].rows == [(100,)]
        assert result["selected_datasource_id"] == "ds1"
        assert result["status"] == "thinking"

    def test_execute_sql_no_sql_returns_error(self, agent_state):
        """execute_sql_node should return error when no SQL is present."""
        from nl2sql.agent.nodes.execute import execute_sql_node

        agent_state.sql = None
        result = execute_sql_node(agent_state)

        assert result["execution_result"] is not None
        assert result["execution_result"].success is False
        assert result["status"] == "failed"

    def test_execute_sql_failure_adds_react_thought(self, agent_state, mock_executor):
        """execute_sql_node should add error to react_thoughts on failure."""
        from nl2sql.agent.nodes.execute import execute_sql_node

        sql = "SELECT * FROM bad_table"
        agent_state.sql = sql
        mock_executor.set_response(
            sql,
            ExecutionResult(
                success=False,
                sql=sql,
                error="Table 'bad_table' doesn't exist",
            ),
        )

        result = execute_sql_node(agent_state)

        assert result["execution_result"].success is False
        assert len(result["react_thoughts"]) > 0
        assert "bad_table" in result["react_thoughts"][0].observation.lower() or \
               result["react_thoughts"][0].action == "execute_sql"

    def test_execute_sql_sends_events(self, agent_state, mock_executor):
        """execute_sql_node should send executing and executed events."""
        from nl2sql.agent.nodes.execute import execute_sql_node

        sql = "SELECT 1"
        agent_state.sql = sql
        mock_executor.set_response(
            sql,
            ExecutionResult(success=True, sql=sql, columns=["1"], rows=[(1,)], row_count=1),
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        execute_sql_node(agent_state)

        event_types = [call[0][0] for call in event_callback.call_args_list]
        assert "sql_executing" in event_types
        assert "sql_executed" in event_types


# ===========================================================================
# need_retry_conditional
# ===========================================================================

class TestNeedRetryConditional:
    """Tests for the need_retry_conditional edge function."""

    def testsatisfied_goes_to_summarize(self, agent_state):
        """When satisfied, should go to summarize."""
        from nl2sql.agent.nodes.reflect import need_retry_conditional
        agent_state.satisfied = True
        agent_state.needs_revision = False
        agent_state.iteration = 1
        agent_state.max_iterations = 5
        assert need_retry_conditional(agent_state) == "summarize"

    def testneeds_revision_with_iterations_goes_to_generate(self, agent_state):
        """When needs revision and iterations remain, should retry."""
        from nl2sql.agent.nodes.reflect import need_retry_conditional
        agent_state.satisfied = False
        agent_state.needs_revision = True
        agent_state.iteration = 1
        agent_state.max_iterations = 5
        assert need_retry_conditional(agent_state) == "generate_sql"

    def test_max_iterations_goes_to_summarize(self, agent_state):
        """When max iterations reached, should go to summarize."""
        from nl2sql.agent.nodes.reflect import need_retry_conditional
        agent_state.satisfied = False
        agent_state.needs_revision = True
        agent_state.iteration = 5
        agent_state.max_iterations = 5
        assert need_retry_conditional(agent_state) == "summarize"

    def test_neithersatisfied_nor_revision_with_iterations_retries(self, agent_state):
        """Default: if not satisfied and iterations remain, retry."""
        from nl2sql.agent.nodes.reflect import need_retry_conditional
        agent_state.satisfied = False
        agent_state.needs_revision = False
        agent_state.iteration = 1
        agent_state.max_iterations = 5
        assert need_retry_conditional(agent_state) == "generate_sql"


# ===========================================================================
# reflect_node
# ===========================================================================

class TestReflectNode:
    """Tests for reflect_node."""

    def test_reflect_with_execution_result(self, agent_state, mock_executor):
        """reflect_node should analyze execution result and return ReactThought."""
        from nl2sql.agent.nodes.reflect import reflect_node

        agent_state.sql = "SELECT COUNT(*) FROM users"
        agent_state.execution_result = ExecutionResult(
            success=True,
            sql="SELECT COUNT(*) FROM users",
            columns=["total"],
            rows=[(100,)],
            row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "satisfied": True,
                "needs_revision": False,
                "thought": "SQL 正确执行，结果符合用户查询意图。",
                "suggested_fix": "",
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm):
            result = reflect_node(agent_state)

        assert "react_thoughts" in result
        assert len(result["react_thoughts"]) > 0
        assert result["satisfied"] is True
        assert result["needs_revision"] is False
        assert result["iteration"] == agent_state.iteration + 1

    def test_reflectneeds_revision(self, agent_state):
        """reflect_node should detect when SQL needs revision."""
        from nl2sql.agent.nodes.reflect import reflect_node

        agent_state.sql = "SELECT * FROM users"
        agent_state.execution_result = ExecutionResult(
            success=True,
            sql="SELECT * FROM users",
            columns=["id", "name", "email"],
            rows=[(1, "Alice", "a@b.com"), (2, "Bob", "c@d.com")],
            row_count=2,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "satisfied": False,
                "needs_revision": True,
                "thought": "用户要统计总数，但查询返回了所有行，应该用 COUNT(*)。",
                "suggested_fix": "使用 SELECT COUNT(*) FROM users",
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm):
            result = reflect_node(agent_state)

        assert result["satisfied"] is False
        assert result["needs_revision"] is True

    def test_reflect_sends_event(self, agent_state):
        """reflect_node should send reflection event."""
        from nl2sql.agent.nodes.reflect import reflect_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "satisfied": True,
                "needs_revision": False,
                "thought": "OK",
                "suggested_fix": "",
            }),
            model="test-model",
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm):
            reflect_node(agent_state)

        event_types = [call[0][0] for call in event_callback.call_args_list]
        assert "reflection" in event_types


# ===========================================================================
# summarize_node
# ===========================================================================

class TestSummarizeNode:
    """Tests for summarize_node."""

    def test_summarize_success_result(self, agent_state):
        """summarize_node should produce a natural language answer."""
        from nl2sql.agent.nodes.summarize import summarize_node

        agent_state.sql = "SELECT COUNT(*) AS total FROM users"
        agent_state.execution_result = ExecutionResult(
            success=True,
            sql="SELECT COUNT(*) AS total FROM users",
            columns=["total"],
            rows=[(100,)],
            row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="当前系统中共有 100 个用户。",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):
            result = summarize_node(agent_state)

        assert result["final_answer"] is not None
        assert "100" in result["final_answer"]
        assert result["status"] == "done"

    def test_summarize_failed_execution(self, agent_state):
        """summarize_node should return error info when execution failed."""
        from nl2sql.agent.nodes.summarize import summarize_node

        agent_state.sql = "SELECT * FROM bad_table"
        agent_state.execution_result = ExecutionResult(
            success=False,
            sql="SELECT * FROM bad_table",
            error="Table 'bad_table' doesn't exist",
        )

        result = summarize_node(agent_state)

        assert result["final_answer"] is not None
        assert "错误" in result["final_answer"] or "失败" in result["final_answer"] or \
               "bad_table" in result["final_answer"].lower()
        assert result["status"] == "done"

    def test_summarize_sends_events(self, agent_state):
        """summarize_node should send final_result and done events."""
        from nl2sql.agent.nodes.summarize import summarize_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(content="结果为 1。", model="test-model")
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):
            summarize_node(agent_state)

        event_types = [call[0][0] for call in event_callback.call_args_list]
        assert "final_result" in event_types
        assert "done" in event_types
