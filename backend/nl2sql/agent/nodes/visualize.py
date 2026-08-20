"""Visualize node: AI 决定最佳数据展示形式.

根据用户查询、SQL 和执行结果，让 LLM 选择最合适的图表类型，
输出结构化的 VizSpec 配置供前端渲染.
"""
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

VISUALIZE_SYSTEM_PROMPT = """你是一位数据可视化专家。根据用户的问题、SQL 查询和执行结果，
选择最合适的数据展示形式。

支持的图表类型：
- line: 折线图 — 用于时间趋势、变化率、连续数据
- bar: 柱状图 — 用于分类对比、排名、离散数据对比
- pie: 饼图 — 用于占比分布（类别不超过 8 个时使用）
- area: 面积图 — 用于累计趋势、堆叠展示
- metric: 指标卡 — 用于单个核心数值结果
- table: 表格 — 用于明细数据、多列复杂数据、列表

判断规则：
1. 时间维度 + 数值 → line 或 area
2. 分类 + 数值对比 → bar
3. 占比/分布 + 类别少（≤8）→ pie
4. 单个数字/聚合结果 → metric
5. 明细/列表/多列数据 → table
6. 可以输出多个图表，比如"趋势折线图 + 数据表格"
7. 数据只有 1 行且是单值 → 用 metric
8. 数据行数 > 20 且没有明确分类维度 → 优先 table

严格输出 JSON 格式，不要任何其他文字或 Markdown 代码块。格式：
{
  "charts": [
    {
      "type": "line",
      "title": "每月销售额趋势",
      "x_field": "month",
      "y_field": "sales_amount"
    }
  ]
}

每个 chart 必填字段：
- type: 图表类型
- title: 图表标题

根据类型选填：
- line/bar/area: x_field, y_field（或 y_fields 多系列）, stacked
- pie: category_field, value_field
- metric: value_field（可选 title 中说明含义）
- table: （不需要额外字段）
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def _build_data_preview(exec_result, max_rows: int = 50) -> str:
    """Build a compact text preview of execution result for the LLM."""
    if not exec_result or not exec_result.success or not exec_result.rows:
        return "（无数据）"

    lines = [
        f"列: {', '.join(exec_result.columns)}",
        f"总行数: {exec_result.row_count}",
        "数据预览:",
    ]

    for i, row in enumerate(exec_result.rows[:max_rows]):
        lines.append(f"  {i+1}. {', '.join(str(v) for v in row)}")

    if len(exec_result.rows) > max_rows:
        lines.append(f"  ... 还有 {len(exec_result.rows) - max_rows} 行")

    return "\n".join(lines)


def _extract_json(text: str) -> dict | None:
    """从 LLM 输出中提取 JSON 对象。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _validate_viz_spec(data: dict) -> dict | None:
    """校验并规范化 VizSpec 数据."""
    if not isinstance(data, dict):
        return None
    charts = data.get("charts")
    if not isinstance(charts, list) or not charts:
        return None
    valid_charts = []
    valid_types = {"line", "bar", "pie", "area", "metric", "table"}
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        chart_type = chart.get("type")
        if chart_type not in valid_types:
            continue
        if not chart.get("title"):
            chart["title"] = "数据图表"
        clean = {
            "type": chart_type,
            "title": str(chart["title"]),
            "description": str(chart.get("description", "")),
            "x_field": chart.get("x_field"),
            "y_field": chart.get("y_field"),
            "y_fields": chart.get("y_fields", []),
            "category_field": chart.get("category_field"),
            "value_field": chart.get("value_field"),
            "sort": chart.get("sort"),
            "limit": chart.get("limit"),
            "stacked": bool(chart.get("stacked", False)),
            "config": chart.get("config", {}),
        }
        valid_charts.append(clean)
    if not valid_charts:
        return None
    return {"charts": valid_charts}


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def visualize_node(state: dict) -> dict:
    """根据执行结果生成可视化配置.

    Returns:
        dict with viz_spec (dict or None)
    """
    exec_result = state.get("execution_result")
    if exec_result is None or not exec_result.success:
        return {"viz_spec": None}
    if not exec_result.rows or exec_result.row_count == 0:
        return {"viz_spec": None}

    data_preview = _build_data_preview(exec_result, max_rows=30)
    sql = state.get("sql") or ""
    user_query = state.get("user_query") or ""

    user_msg = f"""用户查询：{user_query}

SQL：
```sql
{sql}
```

执行结果：
{data_preview}

请分析以上内容，选择最合适的图表展示形式。输出 JSON 格式。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=VISUALIZE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    try:
        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.2)
        content = response.content.strip()
        parsed = _extract_json(content)
        if parsed is None:
            _send_event(state, "viz_ready", {"charts": [], "note": "parse_failed"})
            return {"viz_spec": None}
        viz_spec = _validate_viz_spec(parsed)
        if viz_spec is None:
            _send_event(state, "viz_ready", {"charts": [], "note": "invalid"})
            return {"viz_spec": None}
        _send_event(state, "viz_ready", viz_spec)
        return {"viz_spec": viz_spec}
    except Exception as e:
        _send_event(state, "viz_ready", {"charts": [], "note": f"error: {str(e)}"})
        return {"viz_spec": None}
