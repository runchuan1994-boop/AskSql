# 思考过程可视化（Thinking Step Visualization）设计文档

## 概述

在前端聊天界面中，以时间线的形式展示 Agent 每个节点（node）的执行过程和结构化输出。用户可以实时看到思考进度，并点击展开查看每个步骤的详细内容。

## 设计目标

- **透明感**：让用户看到 AI 在"做什么"，而不是黑盒等待
- **可调试**：出问题时能快速定位到哪个步骤出了错
- **不干扰**：流式中展开、完成后折叠，保持聊天界面整洁

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 粒度 | 节点级粗粒度 | 信息适度，现有事件基本够用 |
| 布局 | 时间线嵌入消息内 | 和回复内容上下文紧密，无需跳转 |
| 详情 | 结构化详情 | 展示 SQL/意图/探查结果等具体输出，有实际价值 |
| 展开策略 | 流式中展开、完成后自动折叠 | 兼顾进度感和界面整洁度 |

## 后端设计

### 新增 SSE 事件：`step_detail`

每个节点执行状态变化时发送，用于驱动前端时间线 UI。

```json
{
  "step": "intent_analysis",
  "name": "意图分析",
  "status": "completed",
  "duration_ms": 520,
  "detail": { ... }
}
```

字段说明：
- `step`：步骤唯一标识（英文 kebab-case 或 snake_case）
- `name`：中文展示名称
- `status`：`pending` | `active` | `completed` | `error`
- `duration_ms`：该步骤耗时（毫秒），仅 completed/error 时提供
- `detail`：结构化详情，内容因步骤而异

### 各步骤 detail 结构

#### intent_analysis（意图分析）
```json
{
  "action": "data_query",
  "tables": ["orders", "users"],
  "aggregation": "按月统计",
  "dimensions": ["order_date", "amount"],
  "confidence": 0.92
}
```

#### intent_probe（数据探查）
```json
{
  "probed_tables": ["orders"],
  "findings": [
    "orders 表包含 amount 和 order_date 字段",
    "数据范围 2023-01 ~ 2024-12"
  ]
}
```

#### clarification_needed（需要澄清）
```json
{
  "questions": [
    "你想统计的是哪个时间段的销售数据？",
    "需要按什么维度分组？"
  ]
}
```

#### sql_generated（SQL 生成）
```json
{
  "sql": "SELECT DATE_TRUNC('month', order_date) ...",
  "datasource": "main_db"
}
```

#### sql_executing（执行中）
```json
{
  "datasource": "main_db",
  "tables_involved": ["orders"]
}
```

#### sql_executed（执行完成）
```json
{
  "success": true,
  "row_count": 12,
  "duration_ms": 156
}
```

#### reflection（反思）
```json
{
  "satisfied": true,
  "needs_revision": false,
  "thought": "SQL 逻辑正确，结果符合预期"
}
```

#### visualize（图表生成）
```json
{
  "chart_count": 1,
  "chart_types": ["line"],
  "titles": ["月度销售趋势"]
}
```

### 实现方式

在每个 node 函数中，通过现有的 `event_emitter`（或 graph 的 stream mode）emit 一个 `step_detail` 事件。

- **节点开始时**：发送 `status: "active"`
- **节点结束时**：发送 `status: "completed"` + `duration_ms` + `detail`
- **节点出错时**：发送 `status: "error"` + 错误信息

### 现有事件兼容性

现有的 SSE 事件（`intent_analysis`、`sql_generated`、`sql_executed` 等）**全部保留**，它们驱动核心业务逻辑。`step_detail` 是新增的 UI 辅助事件，不影响现有逻辑。

## 前端设计

### 数据模型

新增 `ThinkingStep` 类型（`frontend/src/lib/types.ts`）：

```ts
interface ThinkingStep {
  step: string;
  name: string;
  status: 'pending' | 'active' | 'completed' | 'error';
  duration_ms?: number;
  detail?: Record<string, any>;
  error_message?: string;
}
```

### Hook 改动

在 `useChat` hook 中：
- 新增 `thinkingSteps: ThinkingStep[]` 状态
- 新增 `isThinking: boolean` 状态
- 收到 `step_detail` 事件时，更新对应步骤
- 收到 `chat_done` 事件时，标记思考结束

### 组件设计

#### `ThinkingTimeline`（新组件，替换 `ThinkingIndicator`）

Props:
```ts
{
  steps: ThinkingStep[];
  isStreaming: boolean;
  defaultExpanded?: boolean;
}
```

行为：
- 流式中（`isStreaming=true`）：默认展开，显示完整时间线
- 完成后（`isStreaming=false`）：折叠为一行摘要（"已完成 · 5 步 · 3.2s"），点击可展开
- 每个步骤可单独点击展开/收起详情
- 步骤状态：✓ 绿色（完成）、⟳ 蓝色脉冲（进行中）、○ 灰色（等待）、✗ 红色（错误）

#### StepDetailRenderer（详情渲染器）

根据 `step` 类型选择不同的渲染方式：

| step 类型 | 渲染方式 |
|-----------|----------|
| intent_analysis | 键值对列表 + 置信度进度条 |
| intent_probe | 表名 tags + 发现列表 |
| clarification_needed | 有序问题列表 |
| sql_generated | SQL 代码块 + 复制按钮 |
| sql_executing | 数据源 + 表名 tags |
| sql_executed | 成功/失败状态 + 行数 + 耗时 |
| reflection | 思考文本 + 结果标签 |
| visualize | 图表卡片预览列表 |

未识别的 step 类型：通用 JSON 格式化展示。

### UI 样式

- 时间线左侧 2px 竖线，节点用 10px 圆点标记
- 已完成节点：绿色圆点 + 绿色文字
- 进行中节点：蓝色圆点 + 脉冲动画 + 蓝色文字
- 等待节点：灰色圆点 + 灰色半透明文字
- 错误节点：红色圆点 + 红色文字
- 详情面板：浅灰背景，圆角 8px，内边距 12px

## 改动文件清单

### 后端
- `backend/nl2sql/agent/nodes/intent.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/probe.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/clarify.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/generate.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/execute.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/reflect.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/visualize.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/nodes/summarize.py` — 发送 step_detail 事件
- `backend/nl2sql/agent/state.py` — 新增 step 相关状态字段（可选，视实现方式）

### 前端
- `frontend/src/lib/types.ts` — 新增 ThinkingStep 类型
- `frontend/src/hooks/useChat.ts` — 新增 thinkingSteps 状态 + step_detail 事件处理
- `frontend/src/components/chat/ThinkingTimeline.tsx` — 新组件
- `frontend/src/components/chat/StepDetailRenderer.tsx` — 新组件
- `frontend/src/components/chat/MessageList.tsx` — 替换 ThinkingIndicator 为 ThinkingTimeline

## 非目标

- 不做 LLM reasoning 细粒度展示（如有需要后续迭代）
- 不做完整 trace 的持久化查询（现有 StepLogger 已做）
- 不改动现有 SSE 事件的语义和数据结构
