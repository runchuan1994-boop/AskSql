"""Clarification nodes: decide whether to ask user for clarification."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

from ._step_utils import step_start, step_complete, step_error

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CLARIFY_SYSTEM_PROMPT = """你是一个数据分析师助手，负责判断用户的自然语言查询是否需要进一步澄清。

核心原则：优先推测，谨慎提问。能不问就不问，让模型自己做合理判断。

任务：
1. 根据意图分析结果（ambiguities）、查询改写假设（assumptions）和探查发现（probe_findings），判断是否还有真正需要向用户澄清的问题。
2. 只输出真正高风险、会导致完全错误结果的业务语义层面问题。
3. 能够通过 SQL 探查解决的技术层面歧义不需要澄清。
4. 可以通过合理假设解决的歧义不需要澄清。

以下情况绝对不要澄清，直接做合理假设：
- 时间范围模糊（"最近"、"近期"、"今年"、"一个月"等）→ 假设最近 30 天
- 统计指标不明确（"数据"、"情况"、"怎么样"、"多少"）→ 假设总数/总金额
- 排序方向未指定 → 假设降序
- 聚合方式不明确 → 根据字段语义自动选择
- 表匹配有一定把握（≥50%）→ 选最相关的表
- 维度未指定 → 假设总计（无维度拆分）

只有当存在以下情况时才需要澄清：
- 有 2 个以上完全不同的业务语义解读，且置信度都不高
- 缺少关键业务概念定义，导致结果可能完全错误
- 用户明确说的内容和数据结构完全对不上

输出格式：JSON 数组，每个元素是一个需要澄清的问题字符串。
如果不需要澄清，输出空数组 []。

数量控制：澄清问题最多 2 个，宁缺毋滥。
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
    t0 = step_start(state, "clarify", "澄清判断")

    try:
        intent = state.get("intent")
        ambiguities = intent.ambiguities if intent else []
        confidence = float(intent.confidence) if intent and intent.confidence else 0.0
        probe_findings = state.get("probe_findings", []) or []
        query_assumptions = state.get("query_assumptions", []) or []

        action = intent.action if intent else "query"

        # Fast-path: high confidence → skip clarification entirely
        # 如果置信度 >= 0.7，直接不澄清（即使有少量歧义，也按最可能的理解执行）
        # 注意：connect_datasource 意图不适用快速路径（连接参数必须问清楚）
        is_query = action == "query"
        if is_query and confidence >= 0.7:
            step_complete(state, "clarify", "澄清判断", {
                "needs_clarification": False,
                "questions": [],
                "fast_path": True,
                "reason": f"高置信度 ({confidence:.2f})，跳过澄清",
            }, t0)
            return {
                "clarification_questions": [],
                "awaiting_clarification": False,
            }

        # Fast-path: medium confidence + few ambiguities → skip clarification
        # 如果置信度 >= 0.5 且歧义 <= 1 个，不澄清（query_rewrite 已做合理推测）
        if is_query and confidence >= 0.5 and len(ambiguities) <= 1:
            step_complete(state, "clarify", "澄清判断", {
                "needs_clarification": False,
                "questions": [],
                "fast_path": True,
                "reason": f"中等置信度 ({confidence:.2f}) 且歧义少 ({len(ambiguities)}个)，跳过澄清",
            }, t0)
            return {
                "clarification_questions": [],
                "awaiting_clarification": False,
            }

        # Build probe findings summary
        probe_summary = ""
        if probe_findings:
            lines = ["已进行的探查发现："]
            for f in probe_findings:
                lines.append(f"- {f.action}({f.table}): {f.finding}")
            probe_summary = "\n".join(lines)

        # Build assumptions summary
        assumptions_summary = ""
        if query_assumptions:
            lines = ["已做出的合理假设（查询改写阶段）："]
            for a in query_assumptions:
                lines.append(f"- {a}")
            assumptions_summary = "\n".join(lines)

        # Build user message
        user_query = state["user_query"]
        user_msg_parts = [
            f"用户查询：{user_query}",
            "",
            f"意图置信度：{confidence}",
            f"意图分析发现的歧义：{json.dumps(ambiguities, ensure_ascii=False)}",
        ]
        if assumptions_summary:
            user_msg_parts.extend(["", assumptions_summary])
        if probe_summary:
            user_msg_parts.extend(["", probe_summary])
        user_msg_parts.extend([
            "",
            "请判断是否还需要向用户澄清问题。只输出 JSON 数组格式的问题列表，最多 2 个问题。",
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

        step_complete(state, "clarify", "澄清判断", {
            "needs_clarification": len(questions) > 0,
            "questions": questions,
        }, t0)

        return {
            "clarification_questions": questions,
            "awaiting_clarification": len(questions) > 0,
        }
    except Exception as e:
        step_error(state, "clarify", "澄清判断", str(e), t0)
        raise


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

    Sends a final_result-style event so the frontend can render
    an interactive clarification card for the user.

    The actual waiting / user reply is handled externally.

    Returns:
        dict with status set to "clarifying"
    """
    questions = state.get("clarification_questions", []) or []

    _send_event(state, "final_result", {
        "answer": "",
        "success": False,
        "sql": "",
        "result": None,
        "viz": None,
        "intent": "query",
        "clarification_questions": questions,
    })
    _send_event(state, "done", {"status": "clarifying"})

    return {"status": "clarifying"}
