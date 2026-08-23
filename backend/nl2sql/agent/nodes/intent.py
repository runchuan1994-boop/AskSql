"""Intent analysis node: analyze user query to understand intent."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

from ..state import IntentResult
from ._schema_context import build_compact_schema_context
from ._step_utils import step_start, step_complete, step_error

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

INTENT_SYSTEM_PROMPT = """你是一个资深数据分析师，负责理解用户的自然语言查询意图。

任务：
1. 分析用户查询，识别涉及的表、筛选条件、聚合方式、维度等。
2. 识别查询中的歧义点（仅列真正需要用户决策的高风险业务歧义）。
3. 给出意图分析的置信度。
4. 识别用户意图的动作类型（action）：
   - query: 用户想查询数据（默认）
   - connect_datasource: 用户想连接/创建一个新的数据源
5. 如果 action 是 connect_datasource，从用户消息中提取数据源连接信息（datasource_info）：
   - type: 数据库类型（mysql / postgresql / sqlite 等）
   - host: 主机地址
   - port: 端口号
   - database: 数据库名
   - username: 用户名
   - password: 密码
   - name: 数据源名称

输出格式：严格的 JSON 格式，包含以下字段：
- tables: 数组，每个元素包含 name（表名）和 reason（选择理由）
- filters: 数组，每个元素包含 field（字段名）、operator（操作符）、value（值）
- aggregation: 字符串或 null，聚合方式（count/sum/avg/max/min 等）
- dimensions: 数组，维度字段名列表
- ambiguities: 数组，需要澄清的歧义点列表
- assumptions: 数组，你做出的合理默认假设列表
- confidence: 数字 0-1，置信度
- analysis: 字符串，简要分析说明
- action: 字符串，动作类型（query / connect_datasource），默认为 query
- datasource_info: 对象，数据源连接信息（type/host/port/database/username/password/name），仅当 action 为 connect_datasource 时有效

重要原则：默认假设优先，少歧义多推测。

关于 ambiguities（歧义点）：
- 只列出真正高风险、会导致完全错误结果的业务语义歧义。
- 数量控制：尽量 ≤ 2 个，宁缺毋滥。
- 以下情况不算歧义，不要列出，直接做合理假设，放入 assumptions：
  a) 时间范围模糊（"最近"、"近期"、"今年"、"一个月"等）→ 假设：最近 30 天（或根据上下文合理推断）
  b) 统计指标不明确（"数据"、"情况"、"怎么样"）→ 假设：总数/总金额（根据表的语义类型选择）
  c) 排序方向未指定 → 假设：降序（按最相关的指标）
  d) 表匹配有一定相似度（≥50% 把握）→ 假设：选最相关的表
  e) 聚合方式不明确（"多少"、"统计"）→ 假设：根据字段语义自动选择（金额→SUM，数量→COUNT）
  f) 维度未指定 → 假设：无维度（总计），或选择最自然的维度
  g) 技术层面的歧义（字段名不确定、值不确定等）→ 后续 SQL 探查解决

关于 assumptions（默认假设）：
- 列出你做出的所有合理默认假设，让后续节点知道你的推断。
- 如：["假设'最近'指最近 30 天", "假设'销售数据'指 transactions 表中 payment 类型的交易"]

关于 confidence（置信度）：
- 0.8-1.0：非常确定，表和意图都很明确
- 0.5-0.7：比较确定，有少量歧义但可以合理假设
- 0.3-0.5：不太确定，有多个可能的解读
- 0-0.2：非常不确定，完全不知道用户想要什么
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
    t0 = step_start(state, "intent_analysis", "意图分析")

    try:
        schema_context = build_compact_schema_context(state)
        user_query = state["user_query"]

        user_msg = f"""用户查询：{user_query}

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
                assumptions=parsed.get("assumptions", []),
                confidence=float(parsed.get("confidence", 0.0)),
                raw_analysis=parsed.get("analysis", raw),
                action=parsed.get("action", "query"),
                datasource_info=parsed.get("datasource_info") or {},
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

        # step_detail: 结构化详情
        step_complete(state, "intent_analysis", "意图分析", {
            "action": intent.action,
            "tables": [t.get("name", "") for t in intent.tables if isinstance(t, dict)] or [],
            "aggregation": intent.aggregation,
            "dimensions": intent.dimensions,
            "ambiguities": intent.ambiguities,
            "confidence": intent.confidence,
        }, t0)

        return {"intent": intent, "status": "thinking"}
    except Exception as e:
        step_error(state, "intent_analysis", "意图分析", str(e), t0)
        raise
