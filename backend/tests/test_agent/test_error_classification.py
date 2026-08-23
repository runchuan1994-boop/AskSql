"""测试错误分类函数."""
from __future__ import annotations

import pytest

from nl2sql.agent.tools.datasource_sandbox_tools import classify_connection_error


class TestClassifyConnectionError:
    """测试 classify_connection_error 函数对各种错误的分类."""

    def test_driver_missing_psycopg2(self):
        """PostgreSQL 驱动缺失."""
        error = "No module named 'psycopg2'"
        result = classify_connection_error(error)
        assert result["error_type"] == "driver_missing"
        assert result["missing_module"] == "psycopg2"
        assert result["db_type_hint"] == "postgresql"

    def test_driver_missing_mysql(self):
        """MySQL 驱动缺失."""
        error = "ModuleNotFoundError: No module named 'mysql'"
        result = classify_connection_error(error)
        assert result["error_type"] == "driver_missing"
        assert result["missing_module"] == "mysql"
        assert result["db_type_hint"] == "mysql"

    def test_driver_missing_pymysql(self):
        """pymysql 驱动缺失."""
        error = "No module named 'pymysql'"
        result = classify_connection_error(error)
        assert result["error_type"] == "driver_missing"
        assert result["db_type_hint"] == "mysql"

    def test_authentication_failed_postgres(self):
        """PostgreSQL 密码认证失败."""
        error = 'password authentication failed for user "postgres"'
        result = classify_connection_error(error)
        assert result["error_type"] == "authentication_failed"

    def test_authentication_failed_mysql(self):
        """MySQL 访问被拒绝."""
        error = "Access denied for user 'root'@'localhost'"
        result = classify_connection_error(error)
        assert result["error_type"] == "authentication_failed"

    def test_connection_refused(self):
        """连接被拒绝."""
        error = "Connection refused. Is the server running on host localhost and accepting TCP/IP connections on port 5432?"
        result = classify_connection_error(error)
        assert result["error_type"] == "connection_refused"

    def test_connection_refused_errno(self):
        """errno 格式的连接拒绝."""
        error = "[Errno 61] Connection refused"
        result = classify_connection_error(error)
        assert result["error_type"] == "connection_refused"

    def test_database_not_found_postgres(self):
        """数据库不存在 (PostgreSQL 格式)."""
        error = 'database "nonexistent" does not exist'
        result = classify_connection_error(error)
        assert result["error_type"] == "database_not_found"

    def test_network_timeout(self):
        """网络超时."""
        error = "Connection timed out"
        result = classify_connection_error(error)
        assert result["error_type"] == "network_timeout"

    def test_operation_timed_out(self):
        """操作超时."""
        error = "Operation timed out after 30000 ms"
        result = classify_connection_error(error)
        assert result["error_type"] == "network_timeout"

    def test_unknown_error(self):
        """未知错误."""
        error = "some random error message"
        result = classify_connection_error(error)
        assert result["error_type"] == "unknown"

    def test_human_readable_field(self):
        """每个错误类型都有人类可读描述."""
        errors = [
            ("No module named 'psycopg2'", "缺少数据库驱动模块"),
            ("password authentication failed", "认证失败"),
            ("Connection refused", "连接被拒绝"),
            ('database "x" does not exist', "数据库不存在"),
            ("Connection timed out", "超时"),
            ("random stuff", "未知错误"),
        ]
        for error_msg, expected_substr in errors:
            result = classify_connection_error(error_msg)
            assert expected_substr in result["human_readable"], f"期望包含 '{expected_substr}', 实际: '{result['human_readable']}'"

    def test_error_message_preserved(self):
        """原始错误信息应该被保留."""
        error = "No module named 'psycopg2'"
        result = classify_connection_error(error)
        assert result["error_message"] == error
