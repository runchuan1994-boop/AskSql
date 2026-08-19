"""Probe tools for exploring data in a datasource."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .sql_tool import _get_executor

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

PROBE_TOOLS_DEFINITION: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "probe_distinct",
            "description": "Get distinct values of a column, useful for understanding categorical data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table.",
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Name of the column to probe.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of distinct values to return.",
                        "default": 20,
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the selected or first datasource.",
                    },
                },
                "required": ["table_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_sample",
            "description": "Get sample rows from a table to understand data shape and content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of sample rows to return.",
                        "default": 5,
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the selected or first datasource.",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_min_max",
            "description": "Get the minimum and maximum values of a column.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table.",
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Name of the column.",
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the selected or first datasource.",
                    },
                },
                "required": ["table_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_count",
            "description": "Get the total row count of a table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table.",
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the selected or first datasource.",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def probe_distinct(
    state: "AgentState",
    table_name: str,
    column_name: str,
    limit: int = 20,
    datasource_id: str | None = None,
) -> str:
    """Probe distinct values of a column."""
    executor, err = _get_executor(state, datasource_id)
    if err is not None:
        return f"错误: {err}"

    sql = f"SELECT DISTINCT {column_name} FROM {table_name} LIMIT {limit}"
    result = executor.execute(sql)

    if not result.success:
        return f"probe_distinct 失败:\n  SQL: {result.sql}\n  错误: {result.error}"

    values = [str(row[0]) for row in result.rows]
    lines = [
        f"表 {table_name} 的 {column_name} 列不同值 (最多 {limit} 个):",
    ]
    for i, v in enumerate(values, 1):
        lines.append(f"  {i}. {v}")
    return "\n".join(lines)


def probe_sample(
    state: "AgentState",
    table_name: str,
    limit: int = 5,
    datasource_id: str | None = None,
) -> str:
    """Probe sample rows from a table."""
    executor, err = _get_executor(state, datasource_id)
    if err is not None:
        return f"错误: {err}"

    sql = f"SELECT * FROM {table_name} LIMIT {limit}"
    result = executor.execute(sql)

    if not result.success:
        return f"probe_sample 失败:\n  SQL: {result.sql}\n  错误: {result.error}"

    if not result.rows:
        return f"表 {table_name} 为空。"

    lines = [f"表 {table_name} 样例数据 (前 {len(result.rows)} 行):", ""]
    header = " | ".join(result.columns)
    lines.append(header)
    lines.append("-" * len(header))
    for row in result.rows:
        lines.append(" | ".join(str(v) for v in row))
    return "\n".join(lines)


def probe_min_max(
    state: "AgentState",
    table_name: str,
    column_name: str,
    datasource_id: str | None = None,
) -> str:
    """Probe min/max values of a column."""
    executor, err = _get_executor(state, datasource_id)
    if err is not None:
        return f"错误: {err}"

    sql = f"SELECT MIN({column_name}) AS min_val, MAX({column_name}) AS max_val FROM {table_name}"
    result = executor.execute(sql)

    if not result.success:
        return f"probe_min_max 失败:\n  SQL: {result.sql}\n  错误: {result.error}"

    if not result.rows:
        return f"表 {table_name} 为空，无法获取 {column_name} 的 min/max。"

    min_val, max_val = result.rows[0]
    return (
        f"表 {table_name} 的 {column_name} 列:\n"
        f"  最小值: {min_val}\n"
        f"  最大值: {max_val}"
    )


def probe_count(
    state: "AgentState",
    table_name: str,
    datasource_id: str | None = None,
) -> str:
    """Probe row count of a table."""
    executor, err = _get_executor(state, datasource_id)
    if err is not None:
        return f"错误: {err}"

    sql = f"SELECT COUNT(*) AS cnt FROM {table_name}"
    result = executor.execute(sql)

    if not result.success:
        return f"probe_count 失败:\n  SQL: {result.sql}\n  错误: {result.error}"

    count = result.rows[0][0] if result.rows else 0
    return f"表 {table_name} 的总行数: {count}"


# ---------------------------------------------------------------------------
# Function map
# ---------------------------------------------------------------------------

PROBE_TOOL_FUNCTIONS: dict[str, callable] = {
    "probe_distinct": probe_distinct,
    "probe_sample": probe_sample,
    "probe_min_max": probe_min_max,
    "probe_count": probe_count,
}
