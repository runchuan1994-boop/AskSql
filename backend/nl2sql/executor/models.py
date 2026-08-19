"""SQL execution result models."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    """Result of a SQL query execution."""

    success: bool
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[tuple] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    truncated: bool = False
