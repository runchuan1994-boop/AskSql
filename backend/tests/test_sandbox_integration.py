"""沙盒集成测试 — 验证沙盒能正常创建、通信、执行 SQL、转换 localhost.

这些测试需要 Docker 环境和 nl2sql-sandbox 镜像。
在 CI 环境中如果没有 Docker 会自动跳过。
"""
from __future__ import annotations

import os
import pytest


def _have_docker():
    """检查是否有可用的 Docker 环境."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _have_sandbox_image():
    """检查沙盒镜像是否存在."""
    try:
        import docker
        client = docker.from_env()
        client.images.get(os.getenv("SANDBOX_IMAGE", "nl2sql-sandbox:latest"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _have_docker() or not _have_sandbox_image(),
    reason="Docker or sandbox image not available",
)


class TestSandboxBasics:
    """沙盒基本功能测试."""

    def test_create_and_ping(self):
        """测试沙盒创建和 ping 通信."""
        from sandbox.config import SandboxConfig
        from sandbox.sandbox import Sandbox
        import docker

        config = SandboxConfig(
            enabled=True,
            image=os.getenv("SANDBOX_IMAGE", "nl2sql-sandbox:latest"),
            network_enabled=True,
        )
        client = docker.from_env()
        sb = Sandbox.create(client, config)
        try:
            assert sb.ping(timeout=5), "Sandbox ping failed"
        finally:
            sb.destroy()

    def test_execute_sql_select_1(self):
        """测试沙盒执行 SELECT 1（SQLite 内存库，不需要外部数据库）."""
        from sandbox.config import SandboxConfig
        from sandbox.sandbox import Sandbox
        import docker

        config = SandboxConfig(
            enabled=True,
            image=os.getenv("SANDBOX_IMAGE", "nl2sql-sandbox:latest"),
            network_enabled=True,
        )
        client = docker.from_env()
        sb = Sandbox.create(client, config)
        try:
            result = sb.execute_sql("sqlite:///:memory:", "SELECT 1 AS x")
            assert result.get("success"), f"SQL failed: {result.get('error')}"
            assert result.get("columns") == ["x"]
            assert result.get("rows") == [[1]]
        finally:
            sb.destroy()

    def test_localhost_url_adjustment(self):
        """测试 localhost URL 自动转换为 host.docker.internal."""
        from sandbox.sandbox import Sandbox

        # PostgreSQL
        url = "postgresql://user:pass@localhost:5432/mydb"
        adjusted = Sandbox._adjust_db_url(url)
        assert "host.docker.internal" in adjusted
        assert "localhost" not in adjusted

        # MySQL with 127.0.0.1
        url = "mysql://root:pw@127.0.0.1:3306/test"
        adjusted = Sandbox._adjust_db_url(url)
        assert "host.docker.internal" in adjusted
        assert "127.0.0.1" not in adjusted

        # 远程地址不应该被修改
        url = "postgresql://user:pass@db.example.com:5432/mydb"
        adjusted = Sandbox._adjust_db_url(url)
        assert adjusted == url

        # SQLite 不应该被修改
        url = "sqlite:///data.db"
        adjusted = Sandbox._adjust_db_url(url)
        assert adjusted == url


class TestSandboxPostgresConnection:
    """沙盒连接 PostgreSQL 测试.

    要求本地有 PostgreSQL 在 5432 端口运行（通过 host.docker.internal 访问）。
    """

    @pytest.fixture
    def pg_url(self):
        """从环境变量获取 PostgreSQL URL，或者使用默认的本地测试库."""
        default_url = "postgresql://nl2sql:nl2sql123@localhost:5432/finance_db"
        return os.getenv("TEST_PG_URL", default_url)

    def test_pg_connection_via_sandbox(self, pg_url):
        """测试沙盒能连接到 PostgreSQL（验证 localhost 自动转换）."""
        from sandbox.config import SandboxConfig
        from sandbox.sandbox import Sandbox
        import docker

        config = SandboxConfig(
            enabled=True,
            image=os.getenv("SANDBOX_IMAGE", "nl2sql-sandbox:latest"),
            network_enabled=True,
        )
        client = docker.from_env()
        sb = Sandbox.create(client, config)
        try:
            result = sb.execute_sql(pg_url, "SELECT 1 AS test_val", timeout_seconds=10)
            assert result.get("success"), (
                f"PostgreSQL connection failed: {result.get('error')}\n"
                f"URL: {pg_url}\n"
                "(Ensure PostgreSQL is running on localhost:5432)"
            )
            assert result.get("rows") == [[1]]
        finally:
            sb.destroy()

    def test_pg_test_connection(self, pg_url):
        """测试 test_connection 方法."""
        from sandbox.config import SandboxConfig
        from sandbox.sandbox import Sandbox
        import docker

        config = SandboxConfig(
            enabled=True,
            image=os.getenv("SANDBOX_IMAGE", "nl2sql-sandbox:latest"),
            network_enabled=True,
        )
        client = docker.from_env()
        sb = Sandbox.create(client, config)
        try:
            assert sb.test_connection(pg_url), "test_connection returned False"
        finally:
            sb.destroy()
