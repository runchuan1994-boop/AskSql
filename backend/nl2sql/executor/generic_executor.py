"""Generic SQL executor based on SQLAlchemy."""
from __future__ import annotations

import re
import time
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .base import SQLExecutor
from .models import ExecutionResult

# Allowed statement types (read-only)
_ALLOWED_STATEMENT_PREFIXES = (
    "SELECT",
    "SHOW",
    "DESCRIBE",
    "DESC",
    "EXPLAIN",
    "WITH",
)


class GenericSQLExecutor(SQLExecutor):
    """Generic SQL executor using SQLAlchemy.

    Supports any database that SQLAlchemy can connect to.
    Provides read-only protection and single-statement enforcement.
    """

    def __init__(
        self,
        datasource_id: str,
        db_url: str,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ):
        self.datasource_id = datasource_id
        self._timeout_seconds = timeout_seconds
        self._max_rows = max_rows
        connect_args: dict = {}
        if db_url.startswith("sqlite"):
            connect_args["timeout"] = timeout_seconds
        self._engine: Engine = create_engine(db_url, connect_args=connect_args)

    def _validate_single_statement(self, sql: str) -> tuple[bool, str]:
        """Validate that SQL is a single read-only statement.

        Returns (is_valid, error_message).
        """
        stripped = sql.strip()
        if not stripped:
            return False, "Empty SQL statement"

        # Remove trailing semicolon(s)
        stripped = stripped.rstrip(";").strip()
        if not stripped:
            return False, "Empty SQL statement"

        # Check for multiple statements by looking for semicolons
        # that are not inside string literals or comments
        if _contains_multiple_statements(stripped):
            return False, "Only a single SQL statement is allowed"

        # Check the statement type
        first_word = _get_first_keyword(stripped)
        if first_word.upper() not in _ALLOWED_STATEMENT_PREFIXES:
            return (
                False,
                f"Only read-only statements (SELECT, SHOW, DESCRIBE, EXPLAIN, WITH) "
                f"are allowed, got: {first_word}",
            )

        return True, ""

    def execute(
        self,
        sql: str,
        timeout_seconds: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute a SQL query with validation and error handling."""
        start_time = time.perf_counter()

        # Validate the SQL
        is_valid, error_msg = self._validate_single_statement(sql)
        if not is_valid:
            duration = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                sql=sql,
                error=error_msg,
                duration_ms=duration,
            )

        effective_timeout = timeout_seconds or self._timeout_seconds

        try:
            with self._engine.connect() as conn:
                # Execute with max_rows + 1 to detect truncation
                result = conn.execution_options(
                    timeout=effective_timeout if not self._engine.url.drivername.startswith("sqlite") else None,
                ).execute(text(sql))

                # Fetch up to max_rows + 1 rows
                rows_to_fetch = self._max_rows + 1
                fetched = result.fetchmany(rows_to_fetch)

                truncated = len(fetched) > self._max_rows
                if truncated:
                    fetched = fetched[: self._max_rows]

                columns = list(result.keys()) if result.returns_rows else []
                rows = [tuple(row) for row in fetched]

                duration = (time.perf_counter() - start_time) * 1000
                return ExecutionResult(
                    success=True,
                    sql=sql,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    duration_ms=duration,
                    truncated=truncated,
                )
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                sql=sql,
                error=str(e),
                duration_ms=duration,
            )

    def test_connection(self) -> bool:
        """Test the database connection using SELECT 1."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def _contains_multiple_statements(sql: str) -> bool:
    """Check if SQL contains multiple statements by detecting unescaped semicolons.

    Handles single-quoted, double-quoted strings, and basic line/block comments.
    """
    i = 0
    n = len(sql)
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = sql[i]
        next_ch = sql[i + 1] if i + 1 < n else ""

        # Line comment start
        if not in_single_quote and not in_double_quote and not in_block_comment:
            if ch == "-" and next_ch == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and next_ch == "*":
                in_block_comment = True
                i += 2
                continue

        # Line comment end
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Block comment end
        if in_block_comment:
            if ch == "*" and next_ch == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        # Quote handling (with escape support)
        if ch == "'" and not in_double_quote:
            # Handle '' escape in SQL
            if in_single_quote and next_ch == "'":
                i += 2
                continue
            in_single_quote = not in_single_quote
            i += 1
            continue

        if ch == '"' and not in_single_quote:
            if in_double_quote and next_ch == '"':
                i += 2
                continue
            in_double_quote = not in_double_quote
            i += 1
            continue

        # Semicolon check
        if ch == ";" and not in_single_quote and not in_double_quote:
            # Check if there's anything non-whitespace after
            rest = sql[i + 1:].strip()
            if rest and not rest.startswith("--"):
                return True
            return False

        i += 1

    return False


def _get_first_keyword(sql: str) -> str:
    """Extract the first SQL keyword from a statement.

    Handles leading whitespace, comments, and common keywords.
    """
    # Remove leading comments and whitespace
    s = sql.strip()

    # Remove leading block comments
    while s.startswith("/*"):
        end_idx = s.find("*/")
        if end_idx == -1:
            break
        s = s[end_idx + 2:].lstrip()

    # Remove leading line comments
    while s.startswith("--"):
        end_idx = s.find("\n")
        if end_idx == -1:
            s = ""
            break
        s = s[end_idx + 1:].lstrip()

    # Get first word
    match = re.match(r"(\w+)", s, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""
