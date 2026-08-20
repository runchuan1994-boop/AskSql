"""SQL execution tool for the agent."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

SQL_TOOL_DEFINITION: dict = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": "Execute a SQL query against the datasource and return the results.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to execute.",
                },
                "datasource_id": {
                    "type": "string",
                    "description": "ID of the datasource. If not provided, uses the selected or first datasource.",
                },
            },
            "required": ["sql"],
        },
    },
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_executor(state: "AgentState", datasource_id: str | None = None):
    """Get the executor for a datasource, or None."""
    executors = getattr(state, "datasource_executors", None)
    if not executors:
        return None, "未配置数据源执行器 (datasource_executors)。"

    ds_id = datasource_id or state.get("selected_datasource_id")
    if not ds_id and state["datasources"]:
        ds_id = state["datasources"][0].datasource_id

    if not ds_id:
        return None, "未指定 datasource_id，且找不到可用的数据源。"

    executor = executors.get(ds_id)
    if executor is None:
        return None, f"未找到 datasource_id={ds_id} 对应的执行器。"

    return executor, None


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

def execute_sql(
    state: "AgentState",
    sql: str,
    datasource_id: str | None = None,
) -> str:
    """Execute a SQL query and return a formatted result string."""
    executor, err = _get_executor(state, datasource_id)
    if err is not None:
        return f"错误: {err}"

    try:
        result = executor.execute(sql)
    except Exception as e:
        return f"执行 SQL 时发生异常: {e}"

    if not result.success:
        return f"SQL 执行失败:\n  SQL: {result.sql}\n  错误: {result.error}"

    if not result.rows:
        return f"SQL 执行成功，无返回数据 (影响 {result.row_count} 行，耗时 {result.duration_ms:.2f}ms)。"

    # Format result as text table
    lines = [f"SQL 执行成功 (返回 {result.row_count} 行，耗时 {result.duration_ms:.2f}ms):", ""]
    # Header
    header = " | ".join(result.columns)
    lines.append(header)
    lines.append("-" * len(header))
    for row in result.rows:
        lines.append(" | ".join(str(v) for v in row))

    if result.truncated:
        lines.append("")
        lines.append("(结果已截断)")

    return "\n".join(lines)
