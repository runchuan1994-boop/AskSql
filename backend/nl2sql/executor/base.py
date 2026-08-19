"""SQL executor abstract base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import ExecutionResult


class SQLExecutor(ABC):
    """Abstract base class for SQL executors."""

    datasource_id: str

    @abstractmethod
    def execute(
        self,
        sql: str,
        timeout_seconds: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute a SQL query and return the result."""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Test the database connection. Returns True if successful."""
        ...
