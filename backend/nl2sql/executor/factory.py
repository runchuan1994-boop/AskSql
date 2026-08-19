"""SQL executor factory."""
from __future__ import annotations

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

    In V1, all datasource types use GenericSQLExecutor.
    """
    return GenericSQLExecutor(
        datasource_id=datasource_id,
        db_url=db_url,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
    )
