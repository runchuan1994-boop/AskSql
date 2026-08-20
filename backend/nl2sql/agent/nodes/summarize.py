"""Summarize node: produce final answer from execution result."""
from __future__ import annotations

from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SUMMARIZE_SYSTEM_PROMPT = """你是一位数据分析师助手，负责将 SQL 查询结果用自然语言总结给用户。

规则：
1. 回答简洁明了，3-5 句话即可。
2. 突出关键数字和重要发现。
3. 如果结果为空，如实说明，不要编造数据。
4. 用用户的语言回答（如果用户用中文提问，就用中文回答）。
5. 不要提及 SQL 或技术细节，直接给结论。
6. 如果结果有图表展示，回答中可以自然地引导用户查看图表（例如"各月销量趋势如下图所示"）。
7. 不要直接描述图表的技术细节，把重点放在数据洞察上。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_result_summary(exec_result, max_rows: int = 50) -> str:
    """Build a text summary of the execution result."""
    if not exec_result.success:
        return f"执行失败：{exec_result.error}"

    if not exec_result.rows:
        return f"执行成功，但未返回任何数据 (影响 {exec_result.row_count} 行)。"

    lines = [
        f"查询成功，共返回 {exec_result.row_count} 行数据。",
        "",
        f"列名: {', '.join(exec_result.columns)}",
        "数据:",
    ]

    for i, row in enumerate(exec_result.rows[:max_rows]):
        lines.append(f"  {i+1}. {', '.join(str(v) for v in row)}")

    if len(exec_result.rows) > max_rows:
        lines.append(f"  ... (还有 {len(exec_result.rows) - max_rows} 行，已省略)")

    return "\n".join(lines)


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

def summarize_node(state: dict) -> dict:
    """Summarize the execution result into a natural language answer.

    Returns:
        dict with final_answer and status
    """
    exec_result = state.get("execution_result")

    # Handle failed execution
    if exec_result is None or not exec_result.success:
        error_msg = exec_result.error if exec_result else "没有执行结果。"
        sql = exec_result.sql if exec_result else (state.get("sql") or "")
        final_answer = f"抱歉，查询执行遇到问题：{error_msg}"
        if sql:
            final_answer += f"\n\n尝试执行的 SQL：\n```sql\n{sql}\n```"

        _send_event(state, "final_result", {
            "answer": final_answer,
            "success": False,
            "sql": sql,
            "error": error_msg,
            "viz": None,
        })
        _send_event(state, "done", {"status": "failed", "error": error_msg})

        return {"final_answer": final_answer, "status": "done"}

    # Build result summary for LLM
    result_summary = _build_result_summary(exec_result, max_rows=50)

    user_msg = f"""用户查询：{state["user_query"]}

{result_summary}

请用自然语言总结查询结果，直接回答用户的问题。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=SUMMARIZE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    llm = create_llm_client()
    response = llm.chat(messages, temperature=0.0)

    final_answer = response.content.strip()

    _send_event(state, "final_result", {
        "answer": final_answer,
        "success": True,
        "sql": state.get("sql") or "",
        "row_count": exec_result.row_count,
        "viz": state.get("viz_spec"),
        "result": {
            "columns": exec_result.columns,
            "rows": [list(r) for r in exec_result.rows[:100]],
            "row_count": exec_result.row_count,
            "success": exec_result.success,
            "duration_ms": getattr(exec_result, "duration_ms", None),
            "truncated": len(exec_result.rows) < exec_result.row_count,
        },
    })
    _send_event(state, "done", {"status": "done"})

    return {"final_answer": final_answer, "status": "done"}
