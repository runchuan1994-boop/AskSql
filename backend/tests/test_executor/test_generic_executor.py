"""Tests for GenericSQLExecutor using SQLite in-memory database."""
from __future__ import annotations

import pytest

from nl2sql.executor.factory import create_executor
from nl2sql.executor.generic_executor import GenericSQLExecutor
from nl2sql.executor.models import ExecutionResult


@pytest.fixture
def executor():
    """Create a GenericSQLExecutor with an in-memory SQLite DB and test data."""
    exec_ = GenericSQLExecutor(
        datasource_id="test_sqlite",
        db_url="sqlite:///:memory:",
        timeout_seconds=10,
        max_rows=100,
    )
    # Create test table and insert data
    exec_._engine.execute(
        exec_._engine.dialect.statement_compiler(
            exec_._engine.dialect,
            None,
        ).__class__  # not used
    ) if False else None  # placeholder
    # Use raw connection for setup
    with exec_._engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
        )
        conn.exec_driver_sql(
            "INSERT INTO users (id, name, age) VALUES (1, 'Alice', 30), (2, 'Bob', 25), (3, 'Charlie', 35)"
        )
        conn.commit()
    return exec_


class TestExecutionResult:
    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            sql="SELECT 1",
            columns=["col1"],
            rows=[(1,)],
            row_count=1,
            duration_ms=5.0,
        )
        assert result.success is True
        assert result.sql == "SELECT 1"
        assert result.columns == ["col1"]
        assert result.rows == [(1,)]
        assert result.row_count == 1
        assert result.duration_ms == 5.0
        assert result.error is None
        assert result.truncated is False

    def test_error_result(self):
        result = ExecutionResult(
            success=False,
            sql="BAD SQL",
            error="syntax error",
            duration_ms=2.0,
        )
        assert result.success is False
        assert result.error == "syntax error"
        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0


class TestGenericSQLExecutor:
    def test_select_query(self, executor):
        result = executor.execute("SELECT id, name, age FROM users ORDER BY id")
        assert result.success is True
        assert result.columns == ["id", "name", "age"]
        assert len(result.rows) == 3
        assert result.row_count == 3
        assert result.rows[0] == (1, "Alice", 30)
        assert result.rows[2] == (3, "Charlie", 35)
        assert result.duration_ms > 0
        assert result.truncated is False
        assert result.error is None

    def test_count_query(self, executor):
        result = executor.execute("SELECT COUNT(*) as cnt FROM users")
        assert result.success is True
        assert result.columns == ["cnt"]
        assert result.rows == [(3,)]
        assert result.row_count == 1

    def test_max_rows_truncation(self):
        exec_ = GenericSQLExecutor(
            datasource_id="test_truncate",
            db_url="sqlite:///:memory:",
            timeout_seconds=10,
            max_rows=3,
        )
        with exec_._engine.connect() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE numbers (n INTEGER PRIMARY KEY)"
            )
            for i in range(10):
                conn.exec_driver_sql(f"INSERT INTO numbers (n) VALUES ({i})")
            conn.commit()

        result = exec_.execute("SELECT n FROM numbers ORDER BY n")
        assert result.success is True
        assert result.truncated is True
        assert result.row_count == 3
        assert len(result.rows) == 3
        # Should contain the first 3 rows
        assert result.rows == [(0,), (1,), (2,)]

    def test_sql_error_handling(self, executor):
        result = executor.execute("SELECT * FROM nonexistent_table")
        assert result.success is False
        assert result.error is not None
        assert "nonexistent_table" in result.error.lower() or len(result.error) > 0
        assert result.rows == []
        assert result.row_count == 0

    def test_multi_statement_rejected(self, executor):
        result = executor.execute("SELECT * FROM users; DROP TABLE users;")
        assert result.success is False
        assert result.error is not None
        assert "single" in result.error.lower() or "statement" in result.error.lower()

    def test_non_select_rejected(self, executor):
        result = executor.execute("INSERT INTO users (id, name, age) VALUES (99, 'Test', 20)")
        assert result.success is False
        assert result.error is not None
        assert "read-only" in result.error.lower() or "select" in result.error.lower()

    def test_update_rejected(self, executor):
        result = executor.execute("UPDATE users SET age = 99 WHERE id = 1")
        assert result.success is False
        assert result.error is not None

    def test_delete_rejected(self, executor):
        result = executor.execute("DELETE FROM users WHERE id = 1")
        assert result.success is False
        assert result.error is not None

    def test_show_allowed(self, executor):
        # SQLite doesn't have SHOW, but we can test the validator allows it
        valid, msg = executor._validate_single_statement("SHOW TABLES")
        assert valid is True

    def test_describe_allowed(self, executor):
        valid, msg = executor._validate_single_statement("DESCRIBE users")
        assert valid is True

    def test_explain_allowed(self, executor):
        valid, msg = executor._validate_single_statement("EXPLAIN SELECT * FROM users")
        assert valid is True

    def test_with_allowed(self, executor):
        result = executor.execute(
            "WITH adults AS (SELECT * FROM users WHERE age >= 30) SELECT name FROM adults ORDER BY name"
        )
        assert result.success is True
        assert result.row_count == 2
        assert result.rows == [("Alice",), ("Charlie",)]

    def test_test_connection(self, executor):
        assert executor.test_connection() is True

    def test_datasource_id_property(self, executor):
        assert executor.datasource_id == "test_sqlite"


class TestExecutorFactory:
    def test_create_executor_returns_generic(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_ENABLED", "false")
        exec_ = create_executor(
            datasource_id="ds1",
            datasource_type="mysql",
            db_url="sqlite:///:memory:",
            timeout_seconds=10,
            max_rows=500,
        )
        assert isinstance(exec_, GenericSQLExecutor)
        assert exec_.datasource_id == "ds1"

    def test_create_executor_all_types_use_generic(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_ENABLED", "false")
        for ds_type in ["postgres", "mysql", "sqlite", "bigquery"]:
            exec_ = create_executor(
                datasource_id=f"ds_{ds_type}",
                datasource_type=ds_type,
                db_url="sqlite:///:memory:",
            )
            assert isinstance(exec_, GenericSQLExecutor)
