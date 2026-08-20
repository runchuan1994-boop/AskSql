"""Intent analysis node: analyze user query to understand intent."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client
from nl2sql.schema import SchemaMatcher

from ..state import IntentResult

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

INTENT_SYSTEM_PROMPT = """你是一个资深数据分析师，负责理解用户的自然语言查询意图。

任务：
1. 分析用户查询，识别涉及的表、筛选条件、聚合方式、维度等。
2. 识别查询中的歧义点（业务语义层面，无法通过数据探查解决的）。
3. 给出意图分析的置信度。

输出格式：严格的 JSON 格式，包含以下字段：
- tables: 数组，每个元素包含 name（表名）和 reason（选择理由）
- filters: 数组，每个元素包含 field（字段名）、operator（操作符）、value（值）
- aggregation: 字符串或 null，聚合方式（count/sum/avg/max/min 等）
- dimensions: 数组，维度字段名列表
- ambiguities: 数组，需要澄清的歧义点列表（仅列真正需要澄清的业务语义层面问题）
- confidence: 数字 0-1，置信度
- analysis: 字符串，简要分析说明

注意：ambiguities 只列真正需要用户澄清的业务语义问题。技术层面的歧义（如字段名不确定、数据范围不明确）可以通过后续的 SQL 探查解决，不需要列出。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code block wrappers."""
    text = text.strip()
    # Strip markdown code blocks (```json ... ``` or ``` ... ```)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_schema_context(state: dict) -> str:
    """Build a compact schema context from top matching tables."""
    matcher = SchemaMatcher(state["datasources"])
    matches = matcher.match_tables(state["user_query"], top_k=10)

    if not matches:
        return "（无匹配的表）"

    lines = []
    current_ds = None
    for m in matches:
        if m.datasource_id != current_ds:
            ds = next(
                (d for d in state["datasources"] if d.datasource_id == m.datasource_id),
                None,
            )
            if ds:
                lines.append(f"数据源: {ds.datasource_name} ({ds.datasource_id})")
                current_ds = m.datasource_id

        tbl = m.table
        lines.append(f"  表: {tbl.name} - {tbl.description} (score: {m.score:.1f})")
        # Show column names only (compact)
        col_names = [col.name for col in tbl.columns]
        lines.append(f"    列: {', '.join(col_names)}")

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

def intent_analyze_node(state: dict) -> dict:
    """Analyze user query intent using LLM and schema context.

    Returns:
        dict with "intent" (IntentResult) and "status"
    """
    schema_context = _build_schema_context(state)

    user_msg = f"""用户查询：{state["user_query"]}

可用的表结构（按相关性排序）：
{schema_context}

请分析用户查询的意图，严格按照 JSON 格式输出。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=INTENT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    llm = create_llm_client()
    response = llm.chat(messages, temperature=0.0)

    raw = response.content
    parsed = _parse_json_response(raw)

    if parsed is None:
        # Graceful degradation: return default IntentResult with raw text
        intent = IntentResult(
            tables=[],
            filters=[],
            aggregation=None,
            dimensions=[],
            ambiguities=["无法解析意图分析结果"],
            confidence=0.0,
            raw_analysis=raw,
        )
    else:
        intent = IntentResult(
            tables=parsed.get("tables", []),
            filters=parsed.get("filters", []),
            aggregation=parsed.get("aggregation"),
            dimensions=parsed.get("dimensions", []),
            ambiguities=parsed.get("ambiguities", []),
            confidence=float(parsed.get("confidence", 0.0)),
            raw_analysis=parsed.get("analysis", raw),
        )

    _send_event(state, "intent_analysis", {
        "intent": {
            "tables": intent.tables,
            "filters": intent.filters,
            "aggregation": intent.aggregation,
            "dimensions": intent.dimensions,
            "ambiguities": intent.ambiguities,
            "confidence": intent.confidence,
        },
    })

    return {"intent": intent, "status": "thinking"}
