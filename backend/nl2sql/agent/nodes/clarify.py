"""Clarification nodes: decide whether to ask user for clarification."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CLARIFY_SYSTEM_PROMPT = """你是一个数据分析师助手，负责判断用户的自然语言查询是否需要进一步澄清。

任务：
1. 根据意图分析结果（ambiguities）和探查发现（probe_findings），判断是否还有需要向用户澄清的问题。
2. 只输出真正需要用户决策的业务语义层面的问题。
3. 能够通过 SQL 探查解决的技术层面歧义不需要澄清。

输出格式：JSON 数组，每个元素是一个需要澄清的问题字符串。
如果不需要澄清，输出空数组 []。

示例：
- 输入: ambiguities = ["未指定时间范围"]
- 输出: ["请问你想统计哪个时间段的数据？"]
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list[str]:
    """Parse a JSON array from LLM response, handling markdown wrappers."""
    text = text.strip()
    # Strip markdown code blocks
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(item) for item in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass  # never let callback errors break the agent


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def clarify_node(state: dict) -> dict:
    """Decide whether clarification is needed and generate questions.

    Returns:
        dict with clarification_questions and awaiting_clarification
    """
    intent = state.get("intent")
    ambiguities = intent.ambiguities if intent else []
    probe_findings = state.get("probe_findings", []) or []

    # Build probe findings summary
    probe_summary = ""
    if probe_findings:
        lines = ["已进行的探查发现："]
        for f in probe_findings:
            lines.append(f"- {f.action}({f.table}): {f.finding}")
        probe_summary = "\n".join(lines)

    # Build user message
    user_msg_parts = [
        f"用户查询：{state["user_query"]}",
        "",
        f"意图分析发现的歧义：{json.dumps(ambiguities, ensure_ascii=False)}",
    ]
    if probe_summary:
        user_msg_parts.extend(["", probe_summary])
    user_msg_parts.extend([
        "",
        "请判断是否还需要向用户澄清问题。只输出 JSON 数组格式的问题列表。",
    ])
    user_msg = "\n".join(user_msg_parts)

    messages = [
        Message(role=MessageRole.SYSTEM, content=CLARIFY_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    llm = create_llm_client()
    response = llm.chat(messages, temperature=0.0)

    questions = _parse_json_array(response.content)

    if questions:
        _send_event(state, "clarification_needed", {"questions": questions})

    return {
        "clarification_questions": questions,
        "awaiting_clarification": len(questions) > 0,
    }


def need_clarify_conditional(state: dict) -> str:
    """LangGraph conditional edge: decide next step after clarification check.

    Returns:
        "ask_clarify" if there are unanswered questions, otherwise "generate_sql"
    """
    if state.get("awaiting_clarification", False) and state.get("clarification_questions", []):
        return "ask_clarify"
    return "generate_sql"


def ask_clarify_node(state: dict) -> dict:
    """Mark the agent as waiting for user clarification.

    The actual waiting / user reply is handled externally.

    Returns:
        dict with status set to "clarifying"
    """
    return {"status": "clarifying"}
