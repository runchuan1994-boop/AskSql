"""Tests for agent tools: schema_tools, sql_tool, probe_tools."""
from __future__ import annotations

import pytest

from nl2sql.schema import Column, DatasourceSchema, Schema, Table
from nl2sql.executor import ExecutionResult, SQLExecutor
from nl2sql.agent.state import AgentState
from nl2sql.agent.tools.schema_tools import list_tables, describe_table
from nl2sql.agent.tools.sql_tool import execute_sql
from nl2sql.agent.tools.probe_tools import probe_count


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
        user_query="test query",
    )
    # Attach datasource_executors dict like the real agent would
    state.datasource_executors = {"ds1": mock_executor}
    return state


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------

class TestListTables:
    def test_list_tables_returns_all_tables(self, agent_state):
        """list_tables should return all table names with descriptions."""
        result = list_tables(agent_state)
        assert "users" in result
        assert "orders" in result
        assert "用户表" in result
        assert "订单表" in result

    def test_list_tables_with_specific_datasource(self, agent_state):
        """list_tables accepts an explicit datasource_id."""
        result = list_tables(agent_state, datasource_id="ds1")
        assert "users" in result
        assert "orders" in result

    def test_list_tables_empty_when_no_datasource(self, agent_state):
        """list_tables returns empty info when datasource not found."""
        result = list_tables(agent_state, datasource_id="nonexistent")
        assert "未找到" in result or "not found" in result.lower()


# ---------------------------------------------------------------------------
# describe_table
# ---------------------------------------------------------------------------

class TestDescribeTable:
    def test_describe_table_returns_columns(self, agent_state):
        """describe_table should return column details with primary key marker."""
        result = describe_table(agent_state, table_name="users")
        assert "id" in result
        assert "name" in result
        assert "email" in result
        # Should include primary key marker
        assert "PK" in result or "主键" in result or "primary_key" in result.lower()

    def test_describe_table_returns_column_types(self, agent_state):
        """describe_table should include column type information."""
        result = describe_table(agent_state, table_name="orders")
        assert "DECIMAL" in result or "decimal" in result.lower()
        assert "INT" in result or "int" in result.lower()

    def test_describe_table_not_found(self, agent_state):
        """describe_table should return friendly message for unknown table."""
        result = describe_table(agent_state, table_name="nonexistent_table")
        assert "未找到" in result or "not found" in result.lower()
        # Should not raise an exception
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# execute_sql
# ---------------------------------------------------------------------------

class TestExecuteSql:
    def test_execute_sql_success(self, agent_state, mock_executor):
        """execute_sql should return formatted result text on success."""
        sql = "SELECT * FROM users"
        mock_executor.set_response(
            sql,
            ExecutionResult(
                success=True,
                sql=sql,
                columns=["id", "name"],
                rows=[(1, "Alice"), (2, "Bob")],
                row_count=2,
                duration_ms=1.5,
            ),
        )
        result = execute_sql(agent_state, sql=sql)
        assert "Alice" in result
        assert "Bob" in result
        assert "id" in result
        assert "name" in result

    def test_execute_sql_failure(self, agent_state, mock_executor):
        """execute_sql should return error info on failure."""
        sql = "SELECT * FROM bad_table"
        mock_executor.set_response(
            sql,
            ExecutionResult(
                success=False,
                sql=sql,
                error="Table 'bad_table' doesn't exist",
            ),
        )
        result = execute_sql(agent_state, sql=sql)
        assert "error" in result.lower() or "错误" in result
        assert "bad_table" in result


# ---------------------------------------------------------------------------
# probe_count
# ---------------------------------------------------------------------------

class TestProbeCount:
    def test_probe_count_returns_row_count(self, agent_state, mock_executor):
        """probe_count should execute a COUNT query and return the row count."""
        sql = "select count(*) as cnt from users"
        mock_executor.set_response(
            sql,
            ExecutionResult(
                success=True,
                sql=sql,
                columns=["cnt"],
                rows=[(100,)],
                row_count=1,
            ),
        )
        result = probe_count(agent_state, table_name="users")
        assert "100" in result
        assert "users" in result
