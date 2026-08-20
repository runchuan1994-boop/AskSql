# Smart Visualization（智能可视化）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 NL2SQL Agent 对话中增加智能图表可视化能力——AI 根据查询语义和数据特征自动选择最佳图表类型（折线/柱状/饼图/面积/指标卡/表格），前端用 Recharts 动态渲染，表格支持服务端分页。

**Architecture:** 在 Agent 图中新增 visualize 节点（SQL 执行后、总结前），LLM 分析数据并输出 VizSpec JSON；后端通过 SSE 推送 `viz_ready` 事件；前端新增 ChartRenderer 根据配置动态渲染 Recharts 图表；结果数据支持服务端分页。

**Tech Stack:** Python / LangGraph / FastAPI (后端), React + TypeScript + Recharts (前端)

---

## 任务分解总览

| Task | 范围 | 产出 |
|------|------|------|
| Task 1 | 后端：VizSpec 数据模型 + visualize_node | 节点实现、图接入、单元测试 |
| Task 2 | 后端：summarize 感知可视化 + SSE 事件 | 图表数据透传到 final_result |
| Task 3 | 后端：结果缓存 + 分页 API | 全量结果缓存、分页查询端点 |
| Task 4 | 前端：类型定义 + Recharts 图表组件 | 6 种图表组件 + ChartRenderer |
| Task 5 | 前端：图表集成到聊天 + 表格分页 | 端到端可视化效果 |

---

## Task 1: 后端 — VizSpec 数据模型 + visualize_node

**Files:**
- Create: `backend/nl2sql/agent/nodes/visualize.py`
- Create: `backend/tests/test_agent/test_nodes_visualize.py`
- Modify: `backend/nl2sql/agent/state.py` — add viz_spec field
- Modify: `backend/nl2sql/agent/nodes/__init__.py` — export visualize_node
- Modify: `backend/nl2sql/agent/graph.py` — add visualize node to graph

### Step 1: 给 AgentState 增加 viz_spec 字段

在 `backend/nl2sql/agent/state.py` 的 `AgentState` 类中，`final_answer` 字段上方增加：

```python
    # 可视化
    viz_spec: Optional[dict] = None  # VizSpec dict: {charts: [...]}
```

同时在 `ReactThought` 之后增加一个新的 Pydantic 模型（文件顶部，`class AgentState` 之前）：

```python
class ChartSpec(BaseModel):
    """单个图表配置."""
    type: str  # line / bar / pie / area / metric / table
    title: str
    description: str = ""
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    y_fields: list[str] = Field(default_factory=list)
    category_field: Optional[str] = None
    value_field: Optional[str] = None
    sort: Optional[str] = None  # asc / desc
    limit: Optional[int] = None
    stacked: bool = False
    config: dict = Field(default_factory=dict)


class VizSpec(BaseModel):
    """可视化规范."""
    charts: list[ChartSpec] = Field(default_factory=list)
```

### Step 2: 创建 visualize 节点

创建 `backend/nl2sql/agent/nodes/visualize.py`：

```python
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
    """从 LLM 输出中提取 JSON 对象。

    处理几种情况：
    1. 纯 JSON
    2. JSON 被 ```json ... ``` 包裹
    3. JSON 前后有其他文字
    """
    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _validate_viz_spec(data: dict) -> dict | None:
    """校验并规范化 VizSpec 数据，返回合法的 dict 或 None."""
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

        # 只保留合法字段
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

    # 没有执行结果或执行失败，不做可视化
    if exec_result is None or not exec_result.success:
        return {"viz_spec": None}

    # 没有数据行，不做可视化
    if not exec_result.rows or exec_result.row_count == 0:
        return {"viz_spec": None}

    # 构建 LLM 输入
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

        # 解析 JSON
        parsed = _extract_json(content)
        if parsed is None:
            _send_event(state, "viz_ready", {"charts": [], "note": "parse_failed"})
            return {"viz_spec": None}

        # 校验并规范化
        viz_spec = _validate_viz_spec(parsed)
        if viz_spec is None:
            _send_event(state, "viz_ready", {"charts": [], "note": "invalid"})
            return {"viz_spec": None}

        # 发送 SSE 事件
        _send_event(state, "viz_ready", viz_spec)

        return {"viz_spec": viz_spec}

    except Exception as e:
        # 可视化失败不影响主流程
        _send_event(state, "viz_ready", {"charts": [], "note": f"error: {str(e)}"})
        return {"viz_spec": None}
```

### Step 3: 导出 visualize_node

修改 `backend/nl2sql/agent/nodes/__init__.py`，在 import 列表中加入：

```python
from .visualize import visualize_node
```

在 `__all__` 列表中加入：

```python
    "visualize_node",
```

### Step 4: 将 visualize 节点接入 Agent 图

修改 `backend/nl2sql/agent/graph.py`：

1. 在顶部 import 中增加 `visualize_node`：

```python
from .nodes import (
    intent_analyze_node,
    intent_probe_node,
    clarify_node,
    need_clarify_conditional,
    ask_clarify_node,
    generate_sql_node,
    execute_sql_node,
    reflect_node,
    need_retry_conditional,
    visualize_node,
    summarize_node,
)
```

2. 在 `build_graph()` 函数的 `graph.add_node` 部分增加：

```python
    graph.add_node("visualize", visualize_node)
```

3. 修改边：把 `execute_sql → reflect` 改为 `execute_sql → visualize → reflect`

```python
    # 边: execute_sql → visualize
    graph.add_edge("execute_sql", "visualize")

    # 边: visualize → reflect
    graph.add_edge("visualize", "reflect")
```

（删除原来的 `graph.add_edge("execute_sql", "reflect")` 那行）

4. 注释图结构说明也要更新：

```
    图结构:
        intent_analyze → intent_probe → clarify
                                            ↓
                              ask_clarify  /  generate_sql
                                                      ↓
                                                execute_sql
                                                      ↓
                                                  visualize
                                                      ↓
                                                  reflect
                                              ↙          ↘
                                   generate_sql (重试)   summarize → END
```

### Step 5: NL2SQLAgent.run() 返回值增加 viz

修改 `backend/nl2sql/agent/graph.py` 中 `run()` 方法的 return dict，增加：

```python
            "viz_spec": final_state.get("viz_spec"),
```

### Step 6: 写测试

创建 `backend/tests/test_agent/test_nodes_visualize.py`：

```python
"""Tests for visualize node."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2sql.agent.nodes.visualize import (
    visualize_node,
    _extract_json,
    _validate_viz_spec,
)
from nl2sql.executor import ExecutionResult


# ---------------------------------------------------------------------------
# _extract_json tests
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_pure_json(self):
        text = '{"charts": [{"type": "bar", "title": "test"}]}'
        result = _extract_json(text)
        assert result is not None
        assert result["charts"][0]["type"] == "bar"

    def test_json_in_markdown_code_block(self):
        text = """```json
{"charts": [{"type": "line", "title": "trend"}]}
```"""
        result = _extract_json(text)
        assert result is not None
        assert result["charts"][0]["type"] == "line"

    def test_json_with_surrounding_text(self):
        text = '好的，这是配置：\n{"charts": [{"type":"pie","title":"分布"}]}\n 希望对你有帮助'
        result = _extract_json(text)
        assert result is not None
        assert result["charts"][0]["type"] == "pie"

    def test_invalid_json_returns_none(self):
        result = _extract_json("not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _extract_json("")
        assert result is None


# ---------------------------------------------------------------------------
# _validate_viz_spec tests
# ---------------------------------------------------------------------------

class TestValidateVizSpec:
    def test_valid_line_chart(self):
        data = {"charts": [{"type": "line", "title": "Trend", "x_field": "date", "y_field": "amount"}]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 1
        assert result["charts"][0]["type"] == "line"

    def test_valid_multiple_charts(self):
        data = {"charts": [
            {"type": "bar", "title": "Bar"},
            {"type": "table", "title": "Table"},
        ]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 2

    def test_invalid_type_skipped(self):
        data = {"charts": [
            {"type": "invalid_type", "title": "Bad"},
            {"type": "pie", "title": "Good"},
        ]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 1
        assert result["charts"][0]["type"] == "pie"

    def test_empty_charts_returns_none(self):
        result = _validate_viz_spec({"charts": []})
        assert result is None

    def test_no_charts_key_returns_none(self):
        result = _validate_viz_spec({"foo": "bar"})
        assert result is None

    def test_not_dict_returns_none(self):
        result = _validate_viz_spec("not a dict")
        assert result is None

    def test_default_title_when_missing(self):
        data = {"charts": [{"type": "bar"}]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert result["charts"][0]["title"] == "数据图表"

    def test_all_valid_types_accepted(self):
        for t in ["line", "bar", "pie", "area", "metric", "table"]:
            data = {"charts": [{"type": t, "title": "Test"}]}
            result = _validate_viz_spec(data)
            assert result is not None
            assert result["charts"][0]["type"] == t


# ---------------------------------------------------------------------------
# visualize_node tests
# ---------------------------------------------------------------------------

class TestVisualizeNode:
    def test_no_execution_result_returns_none(self):
        state = {"execution_result": None}
        result = visualize_node(state)
        assert result["viz_spec"] is None

    def test_failed_execution_returns_none(self):
        exec_result = ExecutionResult(
            success=False,
            sql="SELECT 1",
            error="something went wrong",
        )
        state = {"execution_result": exec_result}
        result = visualize_node(state)
        assert result["viz_spec"] is None

    def test_empty_rows_returns_none(self):
        exec_result = ExecutionResult(
            success=True,
            sql="SELECT 1",
            columns=["id"],
            rows=[],
            row_count=0,
        )
        state = {"execution_result": exec_result}
        result = visualize_node(state)
        assert result["viz_spec"] is None

    @patch("nl2sql.agent.nodes.visualize.create_llm_client")
    def test_successful_viz_generation(self, mock_create_llm):
        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(
            content='{"charts": [{"type": "line", "title": "Monthly Sales", "x_field": "month", "y_field": "amount"}]}'
        )
        mock_create_llm.return_value = mock_llm

        exec_result = ExecutionResult(
            success=True,
            sql="SELECT month, amount FROM sales",
            columns=["month", "amount"],
            rows=[["Jan", 100], ["Feb", 200]],
            row_count=2,
        )
        state = {
            "execution_result": exec_result,
            "sql": "SELECT month, amount FROM sales",
            "user_query": "每月销售额是多少",
            "event_callback": None,
        }
        result = visualize_node(state)
        assert result["viz_spec"] is not None
        assert len(result["viz_spec"]["charts"]) == 1
        assert result["viz_spec"]["charts"][0]["type"] == "line"

    @patch("nl2sql.agent.nodes.visualize.create_llm_client")
    def test_llm_returns_invalid_json(self, mock_create_llm):
        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(content="我觉得用柱状图比较好")
        mock_create_llm.return_value = mock_llm

        exec_result = ExecutionResult(
            success=True,
            sql="SELECT name, value FROM t",
            columns=["name", "value"],
            rows=[["a", 1]],
            row_count=1,
        )
        state = {"execution_result": exec_result, "event_callback": None}
        result = visualize_node(state)
        assert result["viz_spec"] is None

    @patch("nl2sql.agent.nodes.visualize.create_llm_client")
    def test_event_callback_fired(self, mock_create_llm):
        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(
            content='{"charts": [{"type": "bar", "title": "Test"}]}'
        )
        mock_create_llm.return_value = mock_llm

        exec_result = ExecutionResult(
            success=True,
            sql="SELECT name, val FROM t",
            columns=["name", "val"],
            rows=[["a", 1]],
            row_count=1,
        )
        callback_called = []

        class FakeState:
            event_callback = lambda e, d: callback_called.append((e, d))
            def get(self, key, default=None):
                return getattr(self, key, default)
            def __getitem__(self, key):
                return getattr(self, key)

        state = FakeState()
        state.execution_result = exec_result
        state.sql = "SELECT name, val FROM t"
        state.user_query = "test"

        # 由于 state 是 Pydantic dict 混合，这里直接用 dict + event_callback key 测试
        state_dict = {
            "execution_result": exec_result,
            "sql": "SELECT name, val FROM t",
            "user_query": "test",
            "event_callback": lambda e, d: callback_called.append((e, d)),
        }
        visualize_node(state_dict)
        assert len(callback_called) > 0
        assert callback_called[0][0] == "viz_ready"
```

### Step 7: 运行测试验证

Run: `cd backend && python -m pytest tests/test_agent/test_nodes_visualize.py -v`
Expected: 所有测试通过（大约 15+ 个）

### Step 8: 运行全量测试确保没破坏现有功能

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 全部通过（201 + 新增的测试）

### Step 9: Commit

```bash
git add backend/nl2sql/agent/nodes/visualize.py backend/nl2sql/agent/nodes/__init__.py backend/nl2sql/agent/state.py backend/nl2sql/agent/graph.py backend/tests/test_agent/test_nodes_visualize.py
git commit -m "feat(agent): add visualize node for AI-powered chart recommendations"
```

---

## Task 2: 后端 — summarize 感知可视化 + chat_service 透传

**Files:**
- Modify: `backend/nl2sql/agent/nodes/summarize.py` — 感知 viz_spec
- Modify: `backend/app/services/chat_service.py` — 保存 viz 到 message result
- Modify: `backend/app/services/session_service.py` — 解析 result_json 中的 viz
- Test: 确保现有测试仍然通过

### Step 1: 修改 summarize 系统提示词

在 `backend/nl2sql/agent/nodes/summarize.py` 的 `SUMMARIZE_SYSTEM_PROMPT` 中，规则部分（第 5 条后）增加：

```
6. 如果结果有图表展示，回答中可以自然地引导用户查看图表（例如"各月销量趋势如下图所示"）。
7. 不要直接描述图表的技术细节，把重点放在数据洞察上。
```

### Step 2: 修改 summarize_node 的 final_result 事件

在 `summarize_node` 函数中，成功路径的 `_send_event(state, "final_result", ...)` 调用，增加 `viz` 字段：

找到成功分支的 `_send_event(state, "final_result", {` 部分（大约在文件末尾），改为：

```python
    viz_spec = state.get("viz_spec")

    _send_event(state, "final_result", {
        "answer": final_answer,
        "success": True,
        "sql": state.get("sql") or "",
        "row_count": exec_result.row_count,
        "viz": viz_spec,
        "result": {
            "columns": exec_result.columns,
            "rows": [list(r) for r in exec_result.rows[:100]],
            "row_count": exec_result.row_count,
            "success": exec_result.success,
            "duration_ms": getattr(exec_result, "duration_ms", None),
            "truncated": len(exec_result.rows) < exec_result.row_count,
        },
    })
```

同样，失败路径的 final_result 也增加 `"viz": None`。

### Step 3: chat_service 保存 viz 数据

修改 `backend/app/services/chat_service.py` 中 `_run_chat_sync` 函数，在构建 `result_dict` 时增加 `viz` 字段：

```python
        result_dict = {
            "columns": exec_result.columns,
            "rows": [list(r) for r in exec_result.rows],
            "row_count": exec_result.row_count,
            "success": exec_result.success,
            "error": exec_result.error,
            "viz": result.get("viz_spec"),  # 新增
        }
```

### Step 4: session_service 兼容 viz 字段

`session_service.add_message` 和 `get_messages` 已经用 json.dumps/json.loads 处理 result_json，所以 viz 会自动序列化/反序列化。确认 `get_messages` 中的 result 解析逻辑能正常处理（已有 `json.loads` + 赋值 `msg["result"]`，无需改动）。

### Step 5: 运行测试

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 全部通过

### Step 6: Commit

```bash
git add backend/nl2sql/agent/nodes/summarize.py backend/app/services/chat_service.py
git commit -m "feat(backend): pass viz spec through chat flow and persist in messages"
```

---

## Task 3: 后端 — 结果缓存 + 分页 API

**Files:**
- Create: `backend/app/services/result_cache.py` — 结果缓存服务
- Modify: `backend/app/api/chat.py` — 新增分页端点
- Modify: `backend/app/services/chat_service.py` — 写入缓存
- Test: `backend/tests/test_services/test_result_cache.py`

### Step 1: 创建结果缓存服务

创建 `backend/app/services/result_cache.py`：

```python
"""查询结果缓存服务.

用于支撑表格分页功能 — 全量结果存在内存缓存中，
前端通过分页接口逐页获取.

TTL: 默认 30 分钟.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock


class ResultCache:
    """带 TTL 的 LRU 结果缓存.

    线程安全，使用 OrderedDict 实现 LRU.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 1800):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()

    def set(self, key: str, value: dict) -> None:
        """存入缓存."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + self._ttl,
            }
            # 超出容量时淘汰最旧的
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def get(self, key: str) -> dict | None:
        """获取缓存，过期返回 None."""
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            if time.time() > item["expires_at"]:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return item["value"]

    def delete(self, key: str) -> None:
        """删除缓存."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# 全局实例
result_cache = ResultCache(max_size=200, ttl_seconds=1800)
```

### Step 2: 写缓存测试

创建 `backend/tests/test_services/test_result_cache.py`：

```python
"""Tests for result cache service."""
from __future__ import annotations

import time

from app.services.result_cache import ResultCache


class TestResultCache:
    def test_set_and_get(self):
        cache = ResultCache()
        cache.set("key1", {"data": "hello"})
        result = cache.get("key1")
        assert result == {"data": "hello"}

    def test_get_missing_returns_none(self):
        cache = ResultCache()
        assert cache.get("nonexistent") is None

    def test_overwrite(self):
        cache = ResultCache()
        cache.set("key", {"v": 1})
        cache.set("key", {"v": 2})
        assert cache.get("key") == {"v": 2}
        assert len(cache) == 1

    def test_delete(self):
        cache = ResultCache()
        cache.set("key", {"v": 1})
        cache.delete("key")
        assert cache.get("key") is None

    def test_clear(self):
        cache = ResultCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0

    def test_max_size_lru_eviction(self):
        cache = ResultCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert len(cache) == 3
        # 加入第 4 个，应该淘汰最旧的 a
        cache.set("d", 4)
        assert len(cache) == 3
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_lru_access_order(self):
        cache = ResultCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # 访问 a，把它移到最新
        cache.get("a")
        # 加入 d，应该淘汰 b（最久未访问）
        cache.set("d", 4)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_ttl_expiry(self):
        cache = ResultCache(ttl_seconds=1)
        cache.set("key", {"data": "temp"})
        assert cache.get("key") == {"data": "temp"}
        time.sleep(1.1)
        assert cache.get("key") is None

    def test_len(self):
        cache = ResultCache()
        assert len(cache) == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2
```

### Step 3: chat_service 写入缓存

修改 `backend/app/services/chat_service.py` 中的 `_run_chat_sync` 函数：

在文件顶部 import 中增加：
```python
from app.services.result_cache import result_cache
```

在构建 `result_dict` 并保存消息之后（`add_message` 调用之后），增加：

```python
        # 将全量结果存入缓存，供分页接口使用
        if exec_result and exec_result.success and exec_result.rows:
            result_cache.set(
                f"msg:{msg_id}",
                {
                    "columns": exec_result.columns,
                    "rows": [list(r) for r in exec_result.rows],
                    "row_count": exec_result.row_count,
                    "success": exec_result.success,
                },
            )
```

注意需要先拿到 `msg_id`。查看 add_message 的返回值 —— 它返回一个 dict 包含 id。所以：

```python
        # 保存助手消息
        msg_result = add_message(
            session_id, "assistant", answer, sql_text=sql, result=result_dict,
        )
        msg_id = msg_result.get("id", "")
```

### Step 4: 新增分页 API 端点

修改 `backend/app/api/chat.py`，增加分页查询结果的端点。

先在顶部增加 import：
```python
from app.services.result_cache import result_cache
```

然后在文件末尾增加：

```python
@router.get("/messages/{message_id}/result")
async def get_result_page(
    message_id: str,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(100, ge=1, le=500, description="每页条数"),
):
    """分页获取查询结果."""
    cached = result_cache.get(f"msg:{message_id}")
    if cached is None:
        raise HTTPException(status_code=404, detail="结果不存在或已过期")

    total = cached["row_count"]
    all_rows = cached["rows"]
    columns = cached["columns"]

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = all_rows[start:end]

    return {
        "columns": columns,
        "rows": page_rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": end < total,
    }
```

别忘了 import `Query`：
```python
from fastapi import APIRouter, HTTPException, Query
```

### Step 5: 运行测试

Run: `cd backend && python -m pytest tests/test_services/test_result_cache.py tests/test_api/test_chat.py -v --tb=short`
Expected: 全部通过

### Step 6: 全量测试

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 全部通过

### Step 7: Commit

```bash
git add backend/app/services/result_cache.py backend/app/api/chat.py backend/app/services/chat_service.py backend/tests/test_services/test_result_cache.py
git commit -m "feat(backend): result cache and paginated result API"
```

---

## Task 4: 前端 — 类型定义 + Recharts 图表组件

**Files:**
- Modify: `frontend/src/lib/types.ts` — 增加 VizSpec, ChartSpec 等类型
- Modify: `frontend/package.json` — 增加 recharts 依赖
- Create: `frontend/src/components/chart/ChartRenderer.tsx`
- Create: `frontend/src/components/chart/LineChartView.tsx`
- Create: `frontend/src/components/chart/BarChartView.tsx`
- Create: `frontend/src/components/chart/PieChartView.tsx`
- Create: `frontend/src/components/chart/AreaChartView.tsx`
- Create: `frontend/src/components/chart/MetricCard.tsx`
- Create: `frontend/src/components/chart/chartUtils.ts`
- Create: `frontend/src/components/chart/ChartGrid.tsx`

### Step 1: 安装 recharts

```bash
cd frontend
npm install recharts@^2.12.0
```

### Step 2: 扩展类型定义

修改 `frontend/src/lib/types.ts`，在文件末尾增加：

```typescript
// ---------- 可视化图表 ----------
export type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'metric' | 'table'

export interface ChartSpec {
  type: ChartType
  title: string
  description?: string
  x_field?: string
  y_field?: string
  y_fields?: string[]
  category_field?: string
  value_field?: string
  sort?: 'asc' | 'desc' | null
  limit?: number
  stacked?: boolean
  config?: Record<string, unknown>
}

export interface VizSpec {
  charts: ChartSpec[]
}

// 分页结果
export interface PaginatedResult {
  columns: string[]
  rows: unknown[][]
  page: number
  page_size: number
  total: number
  has_more: boolean
}
```

然后在 `Message` 接口中增加：
```typescript
  viz?: VizSpec | null
```

同时在 `FinalResultData` 中增加：
```typescript
  viz?: VizSpec
```

### Step 3: 增加 SSE 事件类型

在 `SseEventType` 联合类型中增加：
```typescript
  | 'viz_ready'
```

### Step 4: 创建图表工具函数

创建 `frontend/src/components/chart/chartUtils.ts`：

```typescript
/**
 * 图表工具函数
 */
import type { ChartSpec } from '../../lib/types'

/**
 * 将二维行数据转换为对象数组（Recharts 需要的格式）
 */
export function rowsToObjects(
  columns: string[],
  rows: unknown[][],
  limit?: number,
): Record<string, unknown>[] {
  const data = rows.slice(0, limit ?? rows.length).map((row) => {
    const obj: Record<string, unknown> = {}
    columns.forEach((col, i) => {
      obj[col] = row[i]
    })
    return obj
  })
  return data
}

/**
 * 图表配色（精心调配的高级感色板）
 */
export const CHART_COLORS = [
  '#6366f1', // indigo-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#06b6d4', // cyan-500
  '#ec4899', // pink-500
  '#84cc16', // lime-500
]

/**
 * 获取图表配色（按索引循环）
 */
export function getChartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

/**
 * 判断数值字段的有效 Y 字段列表
 */
export function resolveYFields(chart: ChartSpec, columns: string[]): string[] {
  if (chart.y_fields && chart.y_fields.length > 0) {
    return chart.y_fields.filter((f) => columns.includes(f))
  }
  if (chart.y_field && columns.includes(chart.y_field)) {
    return [chart.y_field]
  }
  // fallback: 找第一个数值列（简单判断：排除 id/date/time 类）
  const numericCols = columns.filter(
    (c) => !/id|date|time|year|month|day|name|category|type$/i.test(c),
  )
  return numericCols.length > 0 ? [numericCols[0]] : [columns[columns.length - 1]]
}

/**
 * 智能判断 X 轴字段
 */
export function resolveXField(chart: ChartSpec, columns: string[]): string {
  if (chart.x_field && columns.includes(chart.x_field)) {
    return chart.x_field
  }
  // fallback: 找第一列或日期类列
  const dateCol = columns.find((c) => /date|time|year|month|day/i.test(c))
  return dateCol ?? columns[0]
}
```

### Step 5: 创建折线图组件

创建 `frontend/src/components/chart/LineChartView.tsx`：

```tsx
/**
 * 折线图组件
 */
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import {
  rowsToObjects,
  getChartColor,
  resolveYFields,
  resolveXField,
} from './chartUtils'

interface LineChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function LineChartView({ chart, columns, rows }: LineChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(255,255,255,0.95)',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontSize: '12px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            }}
          />
          {yFields.length > 1 && (
            <Legend
              wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
              iconType="circle"
            />
          )}
          {yFields.map((field, idx) => (
            <Line
              key={field}
              type="monotone"
              dataKey={field}
              stroke={getChartColor(idx)}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
              name={field}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

### Step 6: 创建柱状图组件

创建 `frontend/src/components/chart/BarChartView.tsx`：

```tsx
/**
 * 柱状图组件
 */
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import {
  rowsToObjects,
  getChartColor,
  resolveYFields,
  resolveXField,
} from './chartUtils'

interface BarChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function BarChartView({ chart, columns, rows }: BarChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            interval={0}
            angle={data.length > 8 ? -30 : 0}
            textAnchor={data.length > 8 ? 'end' : 'middle'}
            height={data.length > 8 ? 50 : 30}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(255,255,255,0.95)',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontSize: '12px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            }}
          />
          {yFields.length > 1 && (
            <Legend
              wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
              iconType="circle"
            />
          )}
          {yFields.map((field, idx) => (
            <Bar
              key={field}
              dataKey={field}
              fill={getChartColor(idx)}
              radius={[4, 4, 0, 0]}
              name={field}
              stackId={chart.stacked ? 'stack' : undefined}
            >
              {yFields.length === 1 &&
                data.map((_, i) => (
                  <Cell key={i} fill={getChartColor(i % 8)} />
                ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
```

### Step 7: 创建饼图组件

创建 `frontend/src/components/chart/PieChartView.tsx`：

```tsx
/**
 * 饼图组件
 */
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import { rowsToObjects, getChartColor, resolveXField } from './chartUtils'

interface PieChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function PieChartView({ chart, columns, rows }: PieChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit ?? 8)

  // 饼图：分类字段 + 数值字段
  const categoryField = chart.category_field ?? resolveXField(chart, columns)
  const valueField =
    chart.value_field ??
    columns.find((c) => c !== categoryField) ??
    columns[0]

  const pieData = data.map((item) => ({
    name: String(item[categoryField] ?? '未知'),
    value: Number(item[valueField]) || 0,
  }))

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={pieData}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={1}
            dataKey="value"
            nameKey="name"
            label={({ name, percent }) =>
              `${name} ${(percent * 100).toFixed(1)}%`
            }
            labelLine={{ stroke: '#d1d5db', strokeWidth: 1 }}
          >
            {pieData.map((_, index) => (
              <Cell key={`cell-${index}`} fill={getChartColor(index)} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(255,255,255,0.95)',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontSize: '12px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            }}
            formatter={(value: number) => value.toLocaleString()}
          />
          <Legend
            layout="vertical"
            verticalAlign="middle"
            align="right"
            wrapperStyle={{ fontSize: '11px' }}
            iconType="circle"
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
```

### Step 8: 创建面积图组件

创建 `frontend/src/components/chart/AreaChartView.tsx`：

```tsx
/**
 * 面积图组件
 */
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import {
  rowsToObjects,
  getChartColor,
  resolveYFields,
  resolveXField,
} from './chartUtils'

interface AreaChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function AreaChartView({ chart, columns, rows }: AreaChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            {yFields.map((field, idx) => (
              <linearGradient
                key={`gradient-${field}`}
                id={`color${idx}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="5%" stopColor={getChartColor(idx)} stopOpacity={0.3} />
                <stop offset="95%" stopColor={getChartColor(idx)} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(255,255,255,0.95)',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontSize: '12px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            }}
          />
          {yFields.length > 1 && (
            <Legend
              wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
              iconType="circle"
            />
          )}
          {yFields.map((field, idx) => (
            <Area
              key={field}
              type="monotone"
              dataKey={field}
              stroke={getChartColor(idx)}
              strokeWidth={2}
              fill={`url(#color${idx})`}
              name={field}
              stackId={chart.stacked ? 'stack' : undefined}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
```

### Step 9: 创建指标卡组件

创建 `frontend/src/components/chart/MetricCard.tsx`：

```tsx
/**
 * 指标卡片组件
 *
 * 用于展示单个核心数值。
 */
import type { ChartSpec } from '../../lib/types'

interface MetricCardProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function MetricCard({ chart, columns, rows }: MetricCardProps) {
  // 取第一行数据
  const firstRow = rows[0]
  let value: unknown = firstRow ? firstRow[0] : null

  // 如果指定了 value_field，找对应列
  if (chart.value_field && firstRow) {
    const idx = columns.indexOf(chart.value_field)
    if (idx >= 0) {
      value = firstRow[idx]
    }
  } else if (columns.length > 1 && firstRow) {
    // 多列时，尝试找最后一列（通常是聚合值）
    value = firstRow[firstRow.length - 1]
  }

  // 格式化数值
  const displayValue =
    typeof value === 'number'
      ? value.toLocaleString()
      : value !== null && value !== undefined
        ? String(value)
        : '—'

  return (
    <div className="flex flex-col justify-center h-40 px-6 bg-gradient-to-br from-indigo-50 to-white rounded-lg border border-indigo-100">
      <div className="text-sm text-gray-500 font-medium mb-2">{chart.title}</div>
      <div className="text-4xl font-bold text-indigo-600 tracking-tight">
        {displayValue}
      </div>
      {chart.description && (
        <div className="text-xs text-gray-400 mt-2">{chart.description}</div>
      )}
    </div>
  )
}
```

### Step 10: 创建 ChartRenderer（图表渲染调度器）

创建 `frontend/src/components/chart/ChartRenderer.tsx`：

```tsx
/**
 * 图表渲染器
 *
 * 根据 ChartSpec 的 type 字段动态选择对应的图表组件渲染。
 * 失败时降级为表格提示。
 */
import { useState, useEffect } from 'react'
import type { ChartSpec } from '../../lib/types'
import { LineChartView } from './LineChartView'
import { BarChartView } from './BarChartView'
import { PieChartView } from './PieChartView'
import { AreaChartView } from './AreaChartView'
import { MetricCard } from './MetricCard'

interface ChartRendererProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

const CHART_TYPE_LABELS: Record<string, string> = {
  line: '折线图',
  bar: '柱状图',
  pie: '饼图',
  area: '面积图',
  metric: '指标卡',
  table: '表格',
}

export function ChartRenderer({ chart, columns, rows }: ChartRendererProps) {
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
  }, [chart.type, columns.length, rows.length])

  if (error) {
    return (
      <div className="h-64 flex flex-col items-center justify-center text-gray-400 text-sm bg-gray-50 rounded-lg">
        <span>图表渲染失败</span>
        <span className="text-xs mt-1">{error}</span>
      </div>
    )
  }

  if (!columns.length || !rows.length) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm bg-gray-50 rounded-lg">
        暂无数据
      </div>
    )
  }

  try {
    switch (chart.type) {
      case 'line':
        return <LineChartView chart={chart} columns={columns} rows={rows} />
      case 'bar':
        return <BarChartView chart={chart} columns={columns} rows={rows} />
      case 'pie':
        return <PieChartView chart={chart} columns={columns} rows={rows} />
      case 'area':
        return <AreaChartView chart={chart} columns={columns} rows={rows} />
      case 'metric':
        return <MetricCard chart={chart} columns={columns} rows={rows} />
      case 'table':
      default:
        // table 类型由外部的 ResultTable 处理，这里不重复渲染
        return null
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : '未知错误'
    // 延迟设置 error 以避免 render 期间 setState
    setTimeout(() => setError(msg), 0)
    return null
  }
}

export { CHART_TYPE_LABELS }
```

### Step 11: 创建 ChartGrid（图表网格容器）

创建 `frontend/src/components/chart/ChartGrid.tsx`：

```tsx
/**
 * 图表网格容器
 *
 * 排列多个图表，自适应宽度。
 * - 1 个图表：全宽
 * - 2 个图表：各占 1/2
 * - 3+ 个图表：各占 1/3（自动换行）
 */
import { BarChart3 } from 'lucide-react'
import type { VizSpec, QueryResult } from '../../lib/types'
import { ChartRenderer } from './ChartRenderer'

interface ChartGridProps {
  viz: VizSpec
  result: QueryResult
}

export function ChartGrid({ viz, result }: ChartGridProps) {
  const charts = viz.charts.filter((c) => c.type !== 'table')

  if (charts.length === 0) {
    return null
  }

  // 图表数据：用结果的前 1000 行
  const maxRowsForChart = 1000
  const chartRows = result.rows.slice(0, maxRowsForChart)
  const isSampled = result.row_count > maxRowsForChart

  const gridCols =
    charts.length === 1
      ? 'grid-cols-1'
      : charts.length === 2
        ? 'grid-cols-1 md:grid-cols-2'
        : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'

  return (
    <div className="space-y-3">
      {isSampled && (
        <div className="text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-md inline-flex items-center gap-1.5">
          <BarChart3 size={12} />
          数据量较大，图表展示前 {maxRowsForChart.toLocaleString()} 行
        </div>
      )}
      <div className={`grid ${gridCols} gap-4`}>
        {charts.map((chart, idx) => (
          <div
            key={`${chart.type}-${idx}`}
            className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm"
          >
            <div className="text-sm font-medium text-gray-700 mb-2">
              {chart.title}
            </div>
            <ChartRenderer
              chart={chart}
              columns={result.columns}
              rows={chartRows}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
```

### Step 12: 验证编译

```bash
cd frontend
npx tsc --noEmit
```

Expected: 没有类型错误

### Step 13: Commit

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/types.ts frontend/src/components/chart/
git commit -m "feat(frontend): add Recharts chart components and ChartRenderer"
```

---

## Task 5: 前端 — 图表集成到聊天 + 表格分页

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx` — 集成图表区域
- Modify: `frontend/src/components/chat/ResultTable.tsx` — 支持分页
- Modify: `frontend/src/hooks/useChat.ts` — 处理 viz_ready / final_result.viz
- Modify: `frontend/src/hooks/useSSE.ts` — 增加 viz_ready 事件
- Modify: `frontend/src/lib/api.ts` — 增加分页 API 方法
- Modify: `frontend/src/lib/types.ts` — 增加分页相关类型

### Step 1: 在 api.ts 中增加分页方法

在 `frontend/src/lib/api.ts` 的聊天部分增加：

```typescript
// ---------- 分页结果 ----------
export async function getResultPage(
  messageId: string,
  page: number,
  pageSize = 100,
): Promise<PaginatedResult> {
  return request<PaginatedResult>(
    `/chat/messages/${encodeURIComponent(messageId)}/result?page=${page}&page_size=${pageSize}`,
  )
}
```

注意 import `PaginatedResult`：
```typescript
import type {
  // ... 现有 import
  PaginatedResult,
} from './types'
```

### Step 2: useSSE 增加 viz_ready 事件

修改 `frontend/src/hooks/useSSE.ts` 中的 `allEvents` 数组，增加 `'viz_ready'`。

### Step 3: useChat 处理可视化数据

修改 `frontend/src/hooks/useChat.ts`：

1. import VizSpec:
```typescript
import type { Message, SseEvent, QueryResult, ThinkingStage, VizSpec } from '../lib/types'
```

2. 在 `handleEvent` 的 switch 中，增加 `viz_ready` case（放在 `sql_executed` 后面、`reflection` 前面）：

```typescript
      case 'viz_ready':
        // 收到可视化配置，提前更新消息
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant' && !last.content) {
            // 已有占位消息，更新 viz
            return [
              ...prev.slice(0, -1),
              { ...last, viz: evt.data as unknown as VizSpec },
            ]
          }
          return prev
        })
        break
```

3. 在 `final_result` case 中，解析 `viz` 并加入消息：

```typescript
      case 'final_result': {
        const answer = (evt.data.answer as string) || ''
        const sql = (evt.data.sql as string) || tempSqlRef.current
        const result = evt.data.result as QueryResult | undefined
        const viz = evt.data.viz as VizSpec | undefined
        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          session_id: '',
          role: 'assistant',
          content: answer,
          sql_text: sql || null,
          result: result || null,
          viz: viz || null,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, assistantMsg])
        setStreamingSql(null)
        tempSqlRef.current = ''
        break
      }
```

注意：把 `final_result` 的处理改成带花括号的 block 形式（因为有 `const` 声明）。

4. 在消息发送后，提前创建一个空的助手消息占位（用于流式展示图表）：

在 `sendMessage` 函数中，追加用户消息后、connect 之前，增加：

```typescript
      // 创建占位助手消息（内容会在 final_result 时填充）
      const placeholderMsg: Message = {
        id: `assistant-placeholder-${Date.now()}`,
        session_id: sessionId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, placeholderMsg])
```

### Step 4: 改造 ResultTable 支持分页

重写 `frontend/src/components/chat/ResultTable.tsx`：

```tsx
/**
 * 查询结果表格（支持分页）
 *
 * 使用 @tanstack/react-table + 服务端分页。
 * 第一页数据从 props.result 读取，后续页通过 API 懒加载。
 */
import { useMemo, useState, useEffect, useCallback } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { QueryResult } from '../../lib/types'
import { getResultPage } from '../../lib/api'

interface ResultTableProps {
  result: QueryResult
  messageId?: string
  defaultPageSize?: number
}

const PREVIEW_ROWS = 100 // 首屏预览行数

export function ResultTable({ result, messageId, defaultPageSize = 100 }: ResultTableProps) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(defaultPageSize)
  const [pageData, setPageData] = useState<unknown[][]>(result.rows.slice(0, PREVIEW_ROWS))
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(result.row_count)

  // 当 result 变化时（比如新消息），重置状态
  useEffect(() => {
    setPage(1)
    setPageData(result.rows.slice(0, PREVIEW_ROWS))
    setTotal(result.row_count)
  }, [result])

  // 加载指定页数据
  const loadPage = useCallback(
    async (targetPage: number) => {
      if (!messageId) return
      // 第一页且数据量小，直接用已有的
      if (targetPage === 1 && result.row_count <= PREVIEW_ROWS) {
        setPageData(result.rows)
        setPage(1)
        return
      }
      setLoading(true)
      try {
        const res = await getResultPage(messageId, targetPage, pageSize)
        setPageData(res.rows)
        setTotal(res.total)
        setPage(targetPage)
      } catch {
        // 失败就保留当前页
      } finally {
        setLoading(false)
      }
    },
    [messageId, pageSize, result],
  )

  const data = useMemo(() => {
    return pageData.map((row, idx) => {
      const obj: Record<string, unknown> = {
        __index: (page - 1) * pageSize + idx + 1,
      }
      result.columns.forEach((col, i) => {
        obj[col] = row[i]
      })
      return obj
    })
  }, [pageData, result.columns, page, pageSize])

  const columnHelper = createColumnHelper<Record<string, unknown>>()

  const columns = useMemo(() => {
    return [
      columnHelper.display({
        id: 'index',
        header: '#',
        cell: (info) => info.row.original.__index,
        size: 50,
      }),
      ...result.columns.map((col) =>
        columnHelper.accessor(col, {
          header: col,
          cell: (info) => {
            const val = info.getValue()
            if (val === null || val === undefined) {
              return <span className="text-gray-400">NULL</span>
            }
            if (typeof val === 'object') {
              return JSON.stringify(val)
            }
            return String(val)
          },
        }),
      ),
    ]
  }, [result.columns, columnHelper])

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    enableColumnResizing: true,
  })

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const canPrev = page > 1
  const canNext = page < totalPages
  const showPagination = total > pageSize

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-3 py-1.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs">
        <span className="text-gray-600 font-medium">查询结果</span>
        <span className="text-gray-400">
          共 {total.toLocaleString()} 行
          {result.duration_ms !== undefined &&
            ` · ${result.duration_ms}ms`}
        </span>
      </div>

      <div className="overflow-x-auto max-h-80 overflow-y-auto">
        {loading ? (
          <div className="h-40 flex items-center justify-center text-gray-400 text-sm">
            加载中...
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0 z-10">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-3 py-2 text-left text-xs font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap"
                      style={{ width: header.getSize() }}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, rowIdx) => (
                <tr
                  key={row.id}
                  className={
                    rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  }
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-3 py-1.5 text-gray-700 border-b border-gray-100 font-mono text-xs"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showPagination && (
        <div className="px-3 py-2 bg-gray-50 border-t border-gray-200 flex items-center justify-between text-xs">
          <div className="text-gray-500">
            第 {page} / {totalPages} 页
          </div>
          <div className="flex items-center gap-1">
            <button
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white transition-colors"
              onClick={() => loadPage(page - 1)}
              disabled={!canPrev || loading}
            >
              <ChevronLeft size={14} />
            </button>
            <select
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 bg-white"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
            >
              <option value={50}>50 条/页</option>
              <option value={100}>100 条/页</option>
              <option value={200}>200 条/页</option>
              <option value={500}>500 条/页</option>
            </select>
            <button
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white transition-colors"
              onClick={() => loadPage(page + 1)}
              disabled={!canNext || loading}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

### Step 5: ChatMessage 集成图表

修改 `frontend/src/components/chat/ChatMessage.tsx`：

1. import ChartGrid:
```typescript
import { ChartGrid } from '../chart/ChartGrid'
```

2. 在 SQL 代码块和结果表格之间，增加图表区域：

```tsx
        {/* 图表区域 */}
        {message.viz && message.viz.charts.length > 0 && message.result && (
          <div className="mt-3 w-full">
            <ChartGrid viz={message.viz} result={message.result} />
          </div>
        )}
```

放在 `{/* SQL 代码块 */}` 之后、`{/* 查询结果表格 */}` 之前。

### Step 6: 传递 messageId 给 ResultTable

修改 `ChatMessage.tsx` 中 `ResultTable` 的调用，传入 `messageId`：

```tsx
            <ResultTable result={message.result} messageId={message.id} />
```

### Step 7: 前端构建验证

```bash
cd frontend
npm run build
```

Expected: 构建成功

### Step 8: 后端测试验证

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

Expected: 全部通过

### Step 9: Commit

```bash
git add frontend/src/components/chat/ChatMessage.tsx frontend/src/components/chat/ResultTable.tsx frontend/src/hooks/useChat.ts frontend/src/hooks/useSSE.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): integrate charts into chat and add table pagination"
```

---

## 完成清单

- [ ] Task 1: 后端 — VizSpec 数据模型 + visualize_node
- [ ] Task 2: 后端 — summarize 感知可视化 + chat_service 透传
- [ ] Task 3: 后端 — 结果缓存 + 分页 API
- [ ] Task 4: 前端 — 类型定义 + Recharts 图表组件
- [ ] Task 5: 前端 — 图表集成到聊天 + 表格分页
