"""Query rewrite node: resolve ambiguities by making reasonable assumptions.

当意图有一定歧义但置信度不是特别低时，不直接问用户，
而是做最合理的推测，生成改写后的查询和假设说明。
这样可以显著减少澄清次数，提升用户体验。
"""
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

REWRITE_SYSTEM_PROMPT = """你是一个数据分析师助手，负责对用户的模糊查询进行合理推测和改写。

任务：
1. 分析用户查询中的模糊之处，做出最合理的默认假设。
2. 将模糊查询改写为明确、具体的查询语句。
3. 列出你做出的所有假设，方便后续向用户说明。

改写原则（优先假设）：
- 时间模糊（"最近"、"近期"、"一个月"、"今年"等）→ 假设：最近 30 天
- 指标模糊（"数据"、"情况"、"怎么样"、"多少"等）→ 假设：总数 + 总金额（金额类表）/ 总数（非金额类表）
- 排序方向未指定 → 假设：降序（按最相关指标）
- 聚合方式不明确 → 假设：根据字段语义自动选择（金额→SUM，数量→COUNT）
- 维度未指定 → 假设：总计（无维度拆分）
- 业务术语模糊但能匹配到最相关的表 → 假设：选最相关的表

输出格式：严格的 JSON 格式，包含以下字段：
- rewritten_query: 字符串，改写后的明确查询
- assumptions: 字符串数组，列出所有做出的假设
- should_rewrite: 布尔值，是否进行了改写（如果原查询已经很明确，返回 false）

注意：
- 尽量改写，不要轻易说"需要澄清"——能推测的就推测。
- 假设要合理，符合大多数用户的真实意图。
- 如果原查询已经非常明确，should_rewrite 为 false，assumptions 为空数组。
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

def query_rewrite_node(state: dict) -> dict:
    """对模糊查询进行合理推测改写，减少澄清次数。

    策略：
    - 如果置信度 >= 0.7 且无歧义：跳过（已经很明确）
    - 如果置信度 >= 0.4 且歧义 <= 2 个：进行改写，用合理假设替代澄清
    - 如果置信度 < 0.4 或歧义太多：跳过改写，继续走澄清流程

    Returns:
        dict with rewritten_query and query_assumptions
    """
    t0 = step_start(state, "query_rewrite", "查询改写")

    try:
        intent = state.get("intent")
        user_query = state.get("user_query", "")

        # No intent → skip
        if not intent:
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": "无意图分析结果",
            }, t0)
            return {}

        # connect_datasource 意图不做改写（连接参数不能靠假设）
        action = getattr(intent, "action", "query")
        if action != "query":
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": f"非 query 意图 ({action})，不做改写",
            }, t0)
            return {}

        confidence = float(getattr(intent, "confidence", 0.0))
        ambiguities = getattr(intent, "ambiguities", []) or []

        # High confidence and no ambiguities → already clear, skip rewrite
        if confidence >= 0.7 and len(ambiguities) == 0:
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": "高置信度且无歧义，无需改写",
                "confidence": confidence,
            }, t0)
            return {}

        # Too ambiguous → skip rewrite, let clarify handle it
        if confidence < 0.4 or len(ambiguities) > 2:
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": "置信度过低或歧义过多，交由澄清处理",
                "confidence": confidence,
                "ambiguities_count": len(ambiguities),
            }, t0)
            return {}

        # Build schema context (top matching tables)
        from nl2sql.schema import SchemaMatcher
        matcher = SchemaMatcher(state.get("datasources", []))
        matches = matcher.match_tables(user_query, top_k=5)

        schema_lines = []
        for m in matches[:5]:
            tbl = m.table
            col_names = [c.name for c in tbl.columns[:10]]
            schema_lines.append(f"- {tbl.name} ({tbl.description}): {', '.join(col_names)}")

        schema_context = "\n".join(schema_lines) if schema_lines else "（无匹配表）"

        # Call LLM to rewrite
        intent_assumptions = getattr(intent, "assumptions", []) or []
        assumptions_text = json.dumps(intent_assumptions, ensure_ascii=False) if intent_assumptions else "（无）"

        user_msg = f"""用户原始查询：{user_query}

意图分析结果：
- 置信度：{confidence}
- 识别的歧义点：{json.dumps(ambiguities, ensure_ascii=False)}
- 涉及的表：{json.dumps(intent.tables, ensure_ascii=False)}
- 已做出的默认假设：{assumptions_text}

可用的表结构（按相关性排序）：
{schema_context}

请对用户查询进行合理推测和改写。可以参考意图分析中的假设，
但请给出你自己的判断和更具体的改写。输出 JSON 格式。"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=REWRITE_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.0)

        parsed = _parse_json_response(response.content)

        if parsed is None:
            # Parse failure → skip rewrite gracefully
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": "LLM 返回格式解析失败",
            }, t0)
            return {}

        should_rewrite = bool(parsed.get("should_rewrite", True))
        rewritten_query = parsed.get("rewritten_query", "")
        assumptions = parsed.get("assumptions", []) or []

        if not should_rewrite or not rewritten_query:
            step_complete(state, "query_rewrite", "查询改写", {
                "skipped": True,
                "reason": "LLM 判断无需改写",
            }, t0)
            return {}

        _send_event(state, "query_rewrite", {
            "original_query": user_query,
            "rewritten_query": rewritten_query,
            "assumptions": assumptions,
        })

        step_complete(state, "query_rewrite", "查询改写", {
            "rewritten": True,
            "original": user_query,
            "rewritten_query": rewritten_query,
            "assumptions": assumptions,
            "confidence": confidence,
        }, t0)

        return {
            "original_query": user_query,
            "rewritten_query": rewritten_query,
            "query_assumptions": assumptions,
            "user_query": rewritten_query,  # 下游节点使用改写后的查询
        }
    except Exception as e:
        step_error(state, "query_rewrite", "查询改写", str(e), t0)
        raise
