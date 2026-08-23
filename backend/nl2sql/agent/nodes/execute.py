"""SQL execution node: execute generated SQL."""
from __future__ import annotations

from typing import TYPE_CHECKING

from nl2sql.executor import ExecutionResult

from ..state import ReactThought
from ._step_utils import step_start, step_complete, step_error

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _determine_datasource_id(state: dict) -> str | None:
    """Determine which datasource to execute against.

    Priority:
    1. state.get("selected_datasource_id")
    2. inferred from intent tables
    3. first datasource
    """
    if state.get("selected_datasource_id"):
        return state.get("selected_datasource_id")

    # Try to infer from intent tables
    if state.get("intent") and state.get("intent").tables:
        table_names = [t.get("name", "") for t in state.get("intent").tables if isinstance(t, dict)]
        for ds in state["datasources"]:
            for tname in table_names:
                if ds.db_schema.get_table(tname):
                    return ds.datasource_id

    # Fallback to first datasource
    if state["datasources"]:
        return state["datasources"][0].datasource_id

    return None


def _get_executor(state: dict, datasource_id: str):
    """Get executor from state.datasource_executors."""
    executors = getattr(state, "datasource_executors", None)
    if not executors:
        return None
    return executors.get(datasource_id)


def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def execute_sql_node(state: dict) -> dict:
    """Execute the generated SQL.

    Returns:
        dict with execution_result, react_thoughts, selected_datasource_id, status
    """
    t0 = step_start(state, "sql_executed", "执行查询")

    try:
        if not state.get("sql"):
            result = ExecutionResult(
                success=False,
                sql="",
                error="没有可执行的 SQL 语句。",
            )
            _send_event(state, "sql_execution_error", {"error": "no_sql"})
            step_error(state, "sql_executed", "执行查询", "没有可执行的 SQL 语句", t0)
            return {
                "execution_result": result,
                "status": "failed",
            }

        datasource_id = _determine_datasource_id(state)
        if not datasource_id:
            result = ExecutionResult(
                success=False,
                sql=state.get("sql"),
                error="找不到可用的数据源。",
            )
            _send_event(state, "sql_execution_error", {"error": "no_datasource"})
            step_error(state, "sql_executed", "执行查询", "找不到可用的数据源", t0)
            return {
                "execution_result": result,
                "selected_datasource_id": None,
                "status": "failed",
            }

        executor = _get_executor(state, datasource_id)
        if executor is None:
            result = ExecutionResult(
                success=False,
                sql=state.get("sql"),
                error=f"未找到 datasource_id={datasource_id} 对应的执行器。",
            )
            step_error(state, "sql_executed", "执行查询", f"未找到执行器: {datasource_id}", t0)
            return {
                "execution_result": result,
                "selected_datasource_id": datasource_id,
                "status": "failed",
            }

        _send_event(state, "sql_executing", {"sql": state.get("sql"), "datasource_id": datasource_id})

        try:
            exec_result = executor.execute(state.get("sql"))
        except Exception as e:
            exec_result = ExecutionResult(
                success=False,
                sql=state.get("sql"),
                error=f"执行异常: {e}",
            )

        react_thoughts = []

        if exec_result.success:
            _send_event(state, "sql_executed", {
                "sql": state.get("sql"),
                "row_count": exec_result.row_count,
                "duration_ms": exec_result.duration_ms,
            })
            step_complete(state, "sql_executed", "执行查询", {
                "success": True,
                "row_count": exec_result.row_count,
                "duration_ms": exec_result.duration_ms,
                "datasource_id": datasource_id,
                "columns": exec_result.columns,
            }, t0)
        else:
            # Record failure as a React thought for reflection
            react_thoughts.append(ReactThought(
                thought="SQL 执行失败，需要检查并修正 SQL。",
                action="execute_sql",
                observation=f"错误: {exec_result.error}",
            ))
            _send_event(state, "sql_execution_failed", {
                "sql": state.get("sql"),
                "error": exec_result.error,
            })
            step_error(state, "sql_executed", "执行查询", exec_result.error, t0)

        return {
            "execution_result": exec_result,
            "react_thoughts": react_thoughts,
            "selected_datasource_id": datasource_id,
            "status": "thinking",
        }
    except Exception as e:
        step_error(state, "sql_executed", "执行查询", str(e), t0)
        raise
