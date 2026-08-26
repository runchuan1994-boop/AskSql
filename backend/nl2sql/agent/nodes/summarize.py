"""Summarize node: produce final answer from execution result."""
from __future__ import annotations

from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

from ._step_utils import step_start, step_complete, step_error

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

关于假设说明：
- 如果查询中有做出的合理假设，在回答末尾自然地补充说明。
- 语气要友好，比如"注：我假设你指的是...如果不对可以告诉我调整。"
- 不要显得生硬或像免责声明，要像是在主动确认理解。
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


def _send_event(state: dict | Any, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set.

    Compatible with both dict state (LangGraph runtime) and Pydantic model state (tests).
    """
    if isinstance(state, dict):
        callback = state.get("event_callback")
    else:
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
    t0 = step_start(state, "summarize", "总结回答")

    try:
        exec_result = state.get("execution_result")

        # Handle failed execution
        if exec_result is None or not exec_result.success:
            error_msg = exec_result.error if exec_result else "没有执行结果。"
            sql = exec_result.sql if exec_result else (state.get("sql") or "")
            final_answer = f"抱歉，查询执行遇到问题：{error_msg}"
            if sql:
                final_answer += f"\n\n尝试执行的 SQL：\n```sql\n{sql}\n```"

            # 待确认记忆（即使失败也确认）
            pending_memories = state.get("pending_memories", []) or []
            if pending_memories:
                confirm_lines = ["\n"]
                if len(pending_memories) == 1:
                    mem = pending_memories[0]
                    confirm_lines.append(
                        f"另外，我记下了：{mem.get('content', '')}。"
                    )
                else:
                    confirm_lines.append("另外，我记下了几点：")
                    for i, mem in enumerate(pending_memories):
                        confirm_lines.append(f"{i+1}. {mem.get('content', '')}")
                confirm_lines.append("以后我会注意这些区别 👌")
                final_answer += "\n".join(confirm_lines)

            _send_event(state, "final_result", {
                "answer": final_answer,
                "success": False,
                "sql": sql,
                "error": error_msg,
                "viz": None,
            })
            _send_event(state, "done", {"status": "failed", "error": error_msg})

            step_complete(state, "summarize", "总结回答", {
                "answer_length": len(final_answer),
                "status": "failed",
            }, t0)

            return {"final_answer": final_answer, "status": "done"}

        # Build result summary for LLM
        result_summary = _build_result_summary(exec_result, max_rows=50)

        # Use original query if available (before rewrite) so the answer feels natural
        original_query = state.get("original_query") or state["user_query"]
        query_assumptions = state.get("query_assumptions", []) or []

        user_msg_parts = [
            f"用户查询：{original_query}",
        ]

        if query_assumptions:
            assumptions_text = "\n".join(f"- {a}" for a in query_assumptions)
            user_msg_parts.extend([
                "",
                f"本次查询做出的合理假设：\n{assumptions_text}",
                "请在回答末尾自然地提及这些假设，让用户知道我们是怎么理解的。",
            ])

        user_msg_parts.extend([
            "",
            result_summary,
            "",
            "请用自然语言总结查询结果，直接回答用户的问题。",
        ])

        user_msg = "\n".join(user_msg_parts)

        messages = [
            Message(role=MessageRole.SYSTEM, content=SUMMARIZE_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.0)

        final_answer = response.content.strip()

        # 待确认记忆：在回答末尾追加确认语句
        pending_memories = state.get("pending_memories", []) or []
        if pending_memories:
            confirm_lines = ["\n"]
            if len(pending_memories) == 1:
                mem = pending_memories[0]
                confirm_lines.append(
                    f"另外，我记下了：{mem.get('content', '')}。"
                )
            else:
                confirm_lines.append("另外，我记下了几点：")
                for i, mem in enumerate(pending_memories):
                    confirm_lines.append(f"{i+1}. {mem.get('content', '')}")
            confirm_lines.append("以后我会注意这些区别 👌")
            final_answer += "\n".join(confirm_lines)

        _send_event(state, "final_result", {
            "answer": final_answer,
            "success": True,
            "sql": state.get("sql") or "",
            "row_count": exec_result.row_count,
            "viz": state.get("viz_spec"),
            "query_assumptions": query_assumptions,
            "rewritten_query": state.get("rewritten_query"),
            "pending_memories": pending_memories,
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

        step_complete(state, "summarize", "总结回答", {
            "answer_length": len(final_answer),
            "status": "done",
            "row_count": exec_result.row_count,
        }, t0)

        return {"final_answer": final_answer, "status": "done"}
    except Exception as e:
        step_error(state, "summarize", "总结回答", str(e), t0)
        raise
