"""Reflection node: review SQL execution result and decide retry."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

from ..state import ReactThought

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

REFLECT_SYSTEM_PROMPT = """你是一位严谨的数据分析师，负责审查 SQL 查询的执行结果。

任务：
1. 检查 SQL 是否正确执行
2. 检查结果是否与用户查询匹配
3. 检查是否有遗漏的筛选条件
4. 检查聚合方式和维度是否正确

输出格式：严格的 JSON 格式，包含以下字段：
- satisfied: boolean，是否对结果满意
- needs_revision: boolean，是否需要修正 SQL
- thought: string，你的思考过程说明
- suggested_fix: string，如果需要修正，给出具体的修正建议

注意：只有在确定 SQL 有问题时才标记 needs_revision = true。如果结果正确但数据本身为空，不需要修正。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code block wrappers."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_result_summary(exec_result) -> str:
    """Build a compact summary of execution result."""
    if not exec_result.success:
        return f"执行失败：{exec_result.error}\nSQL: {exec_result.sql}"

    if not exec_result.rows:
        return f"执行成功，但无返回数据 (影响 {exec_result.row_count} 行)。\nSQL: {exec_result.sql}"

    lines = [
        f"执行成功，返回 {exec_result.row_count} 行。",
        f"SQL: {exec_result.sql}",
        "",
        f"列名: {', '.join(exec_result.columns)}",
        "前 10 行数据:",
    ]

    for i, row in enumerate(exec_result.rows[:10]):
        lines.append(f"  {i+1}. {', '.join(str(v) for v in row)}")

    if len(exec_result.rows) > 10:
        lines.append(f"  ... 还有 {len(exec_result.rows) - 10} 行")

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

def reflect_node(state: dict) -> dict:
    """Reflect on the SQL execution result.

    Returns:
        dict with react_thoughts, iteration, _satisfied, _needs_revision
    """
    exec_result = state.get("execution_result")

    # No execution result: skip reflection
    if exec_result is None:
        return {
            "react_thoughts": [],
            "iteration": state.get("iteration", 0) + 1,
            "satisfied": True,
            "needs_revision": False,
        }

    result_summary = _build_result_summary(exec_result)

    # Include previous react thoughts for context
    thoughts_context = ""
    if state.get("react_thoughts", []):
        lines = ["之前的反思："]
        for i, t in enumerate(state.get("react_thoughts", [])[-3:], 1):
            lines.append(f"  {i}. thought: {t.thought}")
            if t.action:
                lines.append(f"     action: {t.action}")
            if t.observation:
                lines.append(f"     observation: {t.observation[:200]}")
        thoughts_context = "\n".join(lines) + "\n\n"

    user_msg = f"""{thoughts_context}用户查询：{state["user_query"]}

{result_summary}

请审查上述 SQL 执行结果，判断是否满足用户查询需求。
严格按照 JSON 格式输出。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=REFLECT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    llm = create_llm_client()
    response = llm.chat(messages, temperature=0.0)

    parsed = _parse_json_response(response.content)

    if parsed is None:
        # Can't parse, assume not satisfied and continue
        thought = ReactThought(
            thought="无法解析反思结果，继续尝试。",
            action="reflect",
            observation=response.content[:200],
        )
        _send_event(state, "reflection", {
            "satisfied": False,
            "needs_revision": True,
            "thought": "解析失败",
        })
        return {
            "react_thoughts": state.get("react_thoughts", []) + [thought],
            "iteration": state.get("iteration", 0) + 1,
            "satisfied": False,
            "needs_revision": True,
        }

    satisfied = bool(parsed.get("satisfied", False))
    needs_revision = bool(parsed.get("needs_revision", False))
    thought_text = str(parsed.get("thought", ""))
    suggested_fix = str(parsed.get("suggested_fix", ""))

    thought = ReactThought(
        thought=thought_text,
        action="reflect",
        observation=f"satisfied={satisfied}, needs_revision={needs_revision}, fix={suggested_fix}",
    )

    _send_event(state, "reflection", {
        "satisfied": satisfied,
        "needs_revision": needs_revision,
        "thought": thought_text,
        "suggested_fix": suggested_fix,
    })

    return {
        "react_thoughts": state.get("react_thoughts", []) + [thought],
        "iteration": state.get("iteration", 0) + 1,
        "satisfied": satisfied,
        "needs_revision": needs_revision,
    }


def need_retry_conditional(state: dict) -> str:
    """LangGraph conditional edge: decide next step after reflection.

    Returns:
        "summarize" or "generate_sql"
    """
    # Max iterations reached
    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "summarize"

    # Satisfied with result
    if state.get("satisfied", False):
        return "summarize"

    # Needs explicit revision
    if state.get("needs_revision", False):
        return "generate_sql"

    # Default: if not satisfied and we have iterations left, retry
    if state.get("iteration", 0) < state.get("max_iterations", 5):
        return "generate_sql"

    return "summarize"
