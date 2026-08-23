"""SQL executor factory."""
from __future__ import annotations

import os

from .base import SQLExecutor
from .generic_executor import GenericSQLExecutor


def create_executor(
    datasource_id: str,
    datasource_type: str,
    db_url: str,
    timeout_seconds: int = 30,
    max_rows: int = 1000,
) -> SQLExecutor:
    """Create a SQL executor based on datasource type.

    如果启用了沙盒（SANDBOX_ENABLED=true），返回 SandboxExecutor，
    所有 SQL 在隔离的 Docker 容器里执行。
    否则返回 GenericSQLExecutor（本地执行）。
    """
    sandbox_enabled = os.getenv("SANDBOX_ENABLED", "false").lower() in ("true", "1", "yes")

    if sandbox_enabled:
        # 延迟导入，避免没有 docker 依赖时 import 失败
        from sandbox.executor import SandboxExecutor
        return SandboxExecutor(
            datasource_id=datasource_id,
            datasource_type=datasource_type,
            db_url=db_url,
            timeout_seconds=timeout_seconds,
        )

    return GenericSQLExecutor(
        datasource_id=datasource_id,
        db_url=db_url,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
    )
