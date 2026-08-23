"""测试 SandboxExecutor（mock 沙盒管理器，不需要真实 Docker）."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sandbox.executor import SandboxExecutor
from sandbox.manager import SandboxManager


@pytest.fixture
def mock_manager():
    manager = MagicMock(spec=SandboxManager)
    return manager


@pytest.fixture
def mock_sandbox():
    sb = MagicMock()
    sb.execute_sql.return_value = {
        "success": True,
        "columns": ["id", "name"],
        "rows": [[1, "alice"], [2, "bob"]],
        "row_count": 2,
        "duration_ms": 10.5,
        "truncated": False,
    }
    sb.test_connection.return_value = True
    sb.install_driver.return_value = True
    return sb


class TestSandboxExecutor:
    def test_execute_success(self, mock_manager, mock_sandbox):
        """执行成功应该返回正确的 ExecutionResult."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="sqlite:///:memory:",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        result = executor.execute("SELECT * FROM users")

        assert result.success is True
        assert result.sql == "SELECT * FROM users"
        assert result.columns == ["id", "name"]
        assert len(result.rows) == 2
        assert result.rows[0] == (1, "alice")
        assert result.row_count == 2
        assert result.duration_ms == 10.5
        assert result.truncated is False
        assert result.error is None

        mock_manager.acquire.assert_called_once()
        mock_manager.release.assert_called_once_with(mock_sandbox)

    def test_execute_failure(self, mock_manager, mock_sandbox):
        """执行失败应该返回错误信息."""
        mock_sandbox.execute_sql.return_value = {
            "success": False,
            "error": "syntax error near 'SELECTT'",
        }
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="sqlite:///:memory:",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        result = executor.execute("SELECTT * FROM users")

        assert result.success is False
        assert "syntax error" in result.error

    def test_test_connection_success(self, mock_manager, mock_sandbox):
        """测试连接成功."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="sqlite:///:memory:",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        assert executor.test_connection() is True

    def test_test_connection_failure(self, mock_manager, mock_sandbox):
        """测试连接失败."""
        mock_sandbox.test_connection.return_value = False
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="bad-url",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        assert executor.test_connection() is False

    def test_postgres_installs_driver(self, mock_manager, mock_sandbox):
        """PostgreSQL 类型应该安装 psycopg2-binary 驱动."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="postgresql://user:pass@localhost/db",
            datasource_type="postgresql",
            manager=mock_manager,
        )
        result = executor.execute("SELECT 1")

        mock_sandbox.install_driver.assert_called_once_with("psycopg2-binary")
        assert result.success is True
        # 第二次执行不应再安装
        executor.execute("SELECT 2")
        assert mock_sandbox.install_driver.call_count == 1

    def test_mysql_installs_driver(self, mock_manager, mock_sandbox):
        """MySQL 类型应该安装 mysql 驱动."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="mysql://user:pass@localhost/db",
            datasource_type="mysql",
            manager=mock_manager,
        )
        executor.execute("SELECT 1")

        mock_sandbox.install_driver.assert_called_once_with("mysql-connector-python")

    def test_sqlite_no_driver_needed(self, mock_manager, mock_sandbox):
        """SQLite 不需要安装驱动."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="ds1",
            db_url="sqlite:///:memory:",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        executor.execute("SELECT 1")

        mock_sandbox.install_driver.assert_not_called()

    def test_datasource_id_attribute(self, mock_manager, mock_sandbox):
        """应该有 datasource_id 属性."""
        mock_manager.acquire.return_value = mock_sandbox

        executor = SandboxExecutor(
            datasource_id="my-ds",
            db_url="sqlite:///:memory:",
            datasource_type="sqlite",
            manager=mock_manager,
        )
        assert executor.datasource_id == "my-ds"
