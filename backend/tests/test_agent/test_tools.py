"""Tests for agent tools: schema_tools, sql_tool, probe_tools, datasource_tools."""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile

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


# ===========================================================================
# DATASOURCE_TOOLS definition
# ===========================================================================

class TestDatasourceToolsDefinition:
    def test_datasource_tools_has_three_tools(self):
        """DATASOURCE_TOOLS should contain exactly 3 tool definitions."""
        from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS
        assert len(DATASOURCE_TOOLS) == 3

    def test_datasource_tool_names(self):
        """DATASOURCE_TOOLS should contain the expected tool names."""
        from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS
        names = [t["function"]["name"] for t in DATASOURCE_TOOLS]
        assert "create_datasource" in names
        assert "test_connection" in names
        assert "import_schema" in names

    def test_create_datasource_required_params(self):
        """create_datasource should require name and type."""
        from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS
        tool = next(t for t in DATASOURCE_TOOLS if t["function"]["name"] == "create_datasource")
        required = tool["function"]["parameters"]["required"]
        assert "name" in required
        assert "type" in required

    def test_test_connection_required_params(self):
        """test_connection should require datasource_id."""
        from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS
        tool = next(t for t in DATASOURCE_TOOLS if t["function"]["name"] == "test_connection")
        required = tool["function"]["parameters"]["required"]
        assert "datasource_id" in required

    def test_import_schema_required_params(self):
        """import_schema should require datasource_id."""
        from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS
        tool = next(t for t in DATASOURCE_TOOLS if t["function"]["name"] == "import_schema")
        required = tool["function"]["parameters"]["required"]
        assert "datasource_id" in required


# ===========================================================================
# Helpers for app-service based tests
# ===========================================================================

def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"
    os.environ["APP_SCHEMAS_DIR"] = os.path.join(tmpdir, "schemas")

    from app.core import config as config_mod
    importlib.reload(config_mod)
    from app.core import database as db_mod
    importlib.reload(db_mod)
    from app.services import project_service as ps_mod
    importlib.reload(ps_mod)
    from app.services import datasource_service as ds_mod
    importlib.reload(ds_mod)
    from app.services import schema_import as si_mod
    importlib.reload(si_mod)

    # Initialize database tables
    db_mod.init_db()


def _create_project():
    from app.services import project_service
    result = project_service.create_project("Test Project")
    return result["id"]


# ===========================================================================
# execute_datasource_tool - create_datasource
# ===========================================================================

class TestExecuteDatasourceCreate:
    def test_create_datasource_success(self):
        """create_datasource tool should create a datasource and return info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "create_datasource",
                {
                    "name": "My DS",
                    "type": "sqlite",
                    "database": ":memory:",
                },
                project_id,
            )

            assert "创建成功" in result
            assert "My DS" in result
            assert "sqlite" in result

    def test_create_datasource_with_full_params(self):
        """create_datasource tool should accept all connection parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "create_datasource",
                {
                    "name": "MySQL DS",
                    "type": "mysql",
                    "host": "localhost",
                    "port": 3306,
                    "database": "testdb",
                    "username": "root",
                    "password": "secret",
                },
                project_id,
            )

            assert "创建成功" in result
            assert "MySQL DS" in result
            assert "mysql" in result
            assert "localhost" in result


# ===========================================================================
# execute_datasource_tool - test_connection
# ===========================================================================

class TestExecuteDatasourceTestConnection:
    def test_test_connection_success(self):
        """test_connection tool should return success for a valid SQLite memory datasource."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from app.services import datasource_service
            ds = datasource_service.create_datasource(
                project_id=project_id,
                name="Conn Test",
                ds_type="sqlite",
                database=":memory:",
            )

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "test_connection",
                {"datasource_id": ds["id"]},
                project_id,
            )

            assert "成功" in result or "success" in result.lower()

    def test_test_connection_missing_id(self):
        """test_connection should return error when datasource_id is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "test_connection",
                {},
                project_id,
            )

            assert "错误" in result or "缺少" in result

    def test_test_connection_nonexistent(self):
        """test_connection should return failure for nonexistent datasource."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "test_connection",
                {"datasource_id": "nonexistent"},
                project_id,
            )

            assert "失败" in result or "not found" in result.lower()


# ===========================================================================
# execute_datasource_tool - import_schema
# ===========================================================================

class TestExecuteDatasourceImportSchema:
    def test_import_schema_success(self):
        """import_schema tool should import tables from a SQLite database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            # Create a sample SQLite file database
            db_path = os.path.join(tmpdir, "sample.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT)"
            )
            conn.execute(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL)"
            )
            conn.commit()
            conn.close()

            from app.services import datasource_service
            ds = datasource_service.create_datasource(
                project_id=project_id,
                name="Import DS",
                ds_type="sqlite",
                database=db_path,
            )

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "import_schema",
                {"datasource_id": ds["id"]},
                project_id,
            )

            assert "导入成功" in result or "成功" in result
            assert "2" in result  # table count
            assert "users" in result
            assert "orders" in result

    def test_import_schema_missing_id(self):
        """import_schema should return error when datasource_id is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "import_schema",
                {},
                project_id,
            )

            assert "错误" in result or "缺少" in result

    def test_import_schema_nonexistent(self):
        """import_schema should return failure for nonexistent datasource."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "import_schema",
                {"datasource_id": "nonexistent"},
                project_id,
            )

            assert "失败" in result or "not found" in result.lower()


# ===========================================================================
# execute_datasource_tool - unknown tool
# ===========================================================================

class TestExecuteDatasourceUnknownTool:
    def test_unknown_tool_returns_error(self):
        """Unknown tool name should return an error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.tools.datasource_tools import execute_datasource_tool
            result = execute_datasource_tool(
                "nonexistent_tool",
                {},
                project_id,
            )

            assert "错误" in result or "未知" in result
            assert "nonexistent_tool" in result
