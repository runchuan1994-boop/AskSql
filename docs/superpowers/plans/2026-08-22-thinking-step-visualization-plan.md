# 思考过程可视化（Thinking Step Visualization）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端聊天界面中以时间线形式展示 Agent 每个节点的执行过程和结构化输出。

**Architecture:** 后端每个 node 新增 `step_detail` SSE 事件 → 前端 useChat 收集步骤 → ThinkingTimeline 组件渲染时间线（流式中展开，完成后折叠）。

**Tech Stack:** Python (LangGraph nodes), React + TypeScript + TailwindCSS, SSE

---

## 任务清单

### Task 1: 后端 - 新增 step_detail 事件工具函数

创建一个统一的 helper，每个节点都用它来发送 step_detail 事件，避免重复代码。

**Files:**
- Create: `backend/nl2sql/agent/nodes/_step_utils.py`
- Modify: `backend/nl2sql/agent/nodes/__init__.py`

Step detail 事件格式：
```python
{
    "step": "intent_analysis",       # 步骤唯一标识
    "name": "意图分析",              # 中文名称
    "status": "completed",           # active | completed | error
    "duration_ms": 520,              # 耗时（仅 completed/error）
    "detail": { ... }                # 结构化详情
}
```

Helper 函数设计：
- `step_start(state, step_key, step_name)` — 发送 status=active
- `step_complete(state, step_key, step_name, detail, start_time)` — 发送 status=completed + 计算耗时
- `step_error(state, step_key, step_name, error_msg, start_time)` — 发送 status=error

### Task 2: 后端 - intent_analyze 节点发送 step_detail

在 `intent.py` 中，节点开始时发送 active，结束时发送 completed + detail。

Detail 内容：
```python
{
    "action": "query",
    "tables": ["orders", "users"],
    "aggregation": "sum",
    "dimensions": ["order_date"],
    "confidence": 0.92
}
```

### Task 3: 后端 - intent_probe 节点发送 step_detail

在 `probe.py` 中，同上。

Detail 内容：
```python
{
    "probed_tables": ["orders"],
    "findings_count": 3,
    "findings": ["finding1", "finding2", ...]
}
```

### Task 4: 后端 - clarify 节点发送 step_detail

在 `clarify.py` 中。

Detail 内容：
```python
{
    "needs_clarification": true,
    "questions": ["问题1", "问题2"]
}
```

### Task 5: 后端 - generate_sql 节点发送 step_detail

在 `generate.py` 中。

Detail 内容：
```python
{
    "sql": "SELECT ...",
    "datasource": "xxx",
    "iteration": 1
}
```

### Task 6: 后端 - execute_sql 节点发送 step_detail

在 `execute.py` 中（开始+结束各发一次，或一次结束时发）。

Detail 内容：
```python
{
    "success": true,
    "row_count": 12,
    "duration_ms": 156,
    "datasource_id": "xxx"
}
```

### Task 7: 后端 - visualize 节点发送 step_detail

在 `visualize.py` 中。

Detail 内容：
```python
{
    "chart_count": 1,
    "chart_types": ["line"],
    "titles": ["月度销售趋势"]
}
```

### Task 8: 后端 - reflect 节点发送 step_detail

在 `reflect.py` 中。

Detail 内容：
```python
{
    "satisfied": true,
    "needs_revision": false,
    "thought": "SQL 逻辑正确",
    "iteration": 1
}
```

### Task 9: 后端 - summarize 节点发送 step_detail

在 `summarize.py` 中。

Detail 内容：
```python
{
    "answer_length": 150,
    "status": "done"
}
```

### Task 10: 前端 - 新增类型定义

在 `types.ts` 中新增 `ThinkingStep` 类型和 `step_detail` 事件类型。

```ts
interface ThinkingStep {
  step: string
  name: string
  status: 'pending' | 'active' | 'completed' | 'error'
  duration_ms?: number
  detail?: Record<string, any>
  error_message?: string
}
```

### Task 11: 前端 - useChat hook 新增 thinkingSteps 状态

在 `useChat.ts` 中：
- 新增 `thinkingSteps: ThinkingStep[]` 状态
- 收到 `step_detail` 事件时更新对应步骤
- `chat_done` 时标记最后一个步骤
- `clearMessages` 时清空

### Task 12: 前端 - ThinkingTimeline 组件

新建 `ThinkingTimeline.tsx`，替换现有的 `ThinkingIndicator`。

功能：
- 垂直时间线样式
- 每个步骤状态：✓ 完成（绿）、⟳ 进行中（蓝脉冲）、○ 等待（灰）、✗ 错误（红）
- 点击步骤展开/收起详情
- 流式中默认展开全部，完成后折叠为摘要条
- 摘要条显示："已完成 · N 步 · X.Xs"

### Task 13: 前端 - StepDetailRenderer 组件

新建 `StepDetailRenderer.tsx`，根据 step 类型渲染不同的详情内容。

支持的类型及渲染方式：
- `intent_analysis` → 键值对列表 + 置信度
- `intent_probe` → 表名 tags + 发现列表
- `clarify` → 有序问题列表
- `sql_generated` → SQL 代码块（复用 SqlDisplay）
- `sql_executed` → 成功/失败 + 行数 + 耗时
- `reflection` → 思考文本 + 标签
- `visualize` → 图表列表
- 默认 → JSON 格式化展示

### Task 14: 前端 - 集成到 MessageList

修改 `MessageList.tsx`：
- 用 `ThinkingTimeline` 替换 `ThinkingIndicator`
- 传入 `thinkingSteps` 和 `isStreaming`

修改 `ChatPanel.tsx`（如有必要）：
- 传递 thinkingSteps 到 MessageList

### Task 15: 验证与联调

1. 启动后端和前端
2. 发送一个查询，观察时间线是否正确展示每个步骤
3. 确认步骤顺序正确、状态变化正确
4. 确认详情展开/折叠正常
5. 确认流式中展开、完成后折叠行为正确
6. 测试错误场景（SQL 执行失败等）
