# 澄清功能（Clarification）

当用户的自然语言查询存在歧义时，Agent 会主动提出澄清问题，用户回复后继续执行查询。

## 功能概述

澄清功能用于解决用户查询中的业务语义层面歧义。当 Agent 分析用户问题后，如果发现无法确定的业务语义（例如"销售数据"在银行数据库中具体指什么），会暂停执行并向用户提出澄清问题。用户回复后，Agent 结合澄清信息继续完成查询。

### 设计原则

- **只澄清业务语义层面的问题**：技术层面的歧义（如字段名、数据范围）通过 SQL 探查自动解决，不需要用户参与
- **对话式交互**：澄清问题作为助手消息展示在对话流中，用户回复方式与普通对话一致
- **无状态恢复**：每次用户消息都启动完整的 Agent 流程，依靠对话历史上下文理解澄清信息（不使用 LangGraph checkpointer）

## 交互流程

```
用户发送模糊查询
      │
      ▼
Agent 分析意图 + 数据探查
      │
      ▼
需要澄清？──────否─────► 生成 SQL → 执行 → 返回结果
      │
      是
      ▼
展示澄清卡片（问题列表）
输入框变为"请回答澄清问题"
      │
      ▼
用户回复澄清内容
      │
      ▼
Agent 重新运行（携带历史对话）
从上下文中理解已澄清的信息
      │
      ▼
生成 SQL → 执行 → 返回结果
```

## 后端实现

### 核心节点

| 节点 | 文件 | 职责 |
|------|------|------|
| `intent_analyze_node` | `nl2sql/agent/nodes/intent.py` | 分析查询意图，识别歧义点 |
| `intent_probe_node` | `nl2sql/agent/nodes/probe.py` | SQL 探查消除技术层面歧义 |
| `clarify_node` | `nl2sql/agent/nodes/clarify.py` | 调用 LLM 判断是否需要澄清，生成问题列表 |
| `ask_clarify_node` | `nl2sql/agent/nodes/clarify.py` | 标记澄清状态，发送 final_result 事件 |

### 状态字段（AgentState）

```python
clarification_questions: list[str] = []   # 需要澄清的问题列表
awaiting_clarification: bool = False      # 是否等待用户澄清
```

### SSE 事件

| 事件 | 触发时机 | 数据 |
|------|----------|------|
| `clarification_needed` | clarify_node 判断需要澄清时 | `{ questions: string[] }` |
| `final_result` | ask_clarify_node 中 | `{ clarification_questions: string[], success: false }` |
| `chat_done` | 流程结束时 | `{ status: "clarifying", success: false }` |

### 消息持久化

澄清状态下的助手消息：
- `content`：友好的引导文本 + 问题列表
- `result.is_clarification`：`true`（标记为澄清消息）
- `result.clarification_questions`：问题列表数组
- `sql_text`：空

用户回复澄清后：
- 新的用户消息正常保存
- Agent 重新运行，从历史对话中理解澄清上下文
- 最终结果作为新的助手消息保存

### 关键文件

- `nl2sql/agent/nodes/clarify.py` - 澄清节点实现
- `nl2sql/agent/graph.py` - Agent 图结构与路由
- `nl2sql/agent/state.py` - 状态定义
- `app/services/chat_service.py` - 聊天服务（clarifying 状态下的消息保存逻辑）

## 前端实现

### 组件结构

```
ChatPanel
├── MessageList
│   └── ChatMessage
│       ├── 消息气泡
│       ├── ClarificationCard （澄清卡片，有澄清问题时显示）
│       ├── SqlDisplay
│       ├── ResultTable
│       └── ChartGrid
└── ChatInput （澄清状态下 placeholder 变化）
```

### ClarificationCard 组件

**位置**：`frontend/src/components/chat/ClarificationCard.tsx`

**Props**：
```typescript
interface ClarificationCardProps {
  questions: string[]   // 澄清问题列表
  resolved?: boolean    // 是否已被回复（已回复时淡化显示）
}
```

**样式**：
- 未回复：琥珀色背景（`bg-amber-50`）+ 琥珀色边框 + 问号图标
- 已回复：灰色背景（`bg-gray-50`）+ 灰色边框 + 对勾图标，透明度降低

### 状态管理（useChat）

新增状态：
```typescript
awaitingClarification: boolean       // 是否处于等待澄清状态
clarificationQuestions: string[]     // 当前澄清问题列表
```

事件处理：
- `clarification_needed`：保存问题列表
- `final_result`：如果是澄清状态，将澄清信息附加到消息上
- `chat_done`：如果 status 为 "clarifying"，保持等待状态
- 用户发送消息时：如果处于澄清状态，标记上一条澄清消息为已回复

### 消息类型扩展

```typescript
interface Message {
  // ... 原有字段
  clarification?: {
    questions: string[]
    resolved?: boolean
  }
}
```

### 关键文件

- `frontend/src/components/chat/ClarificationCard.tsx` - 澄清卡片组件（新建）
- `frontend/src/components/chat/ChatMessage.tsx` - 集成澄清卡片
- `frontend/src/components/chat/ChatPanel.tsx` - 传递澄清状态，调整输入框
- `frontend/src/components/chat/ChatInput.tsx` - 澄清状态 placeholder
- `frontend/src/hooks/useChat.ts` - 澄清状态管理
- `frontend/src/lib/types.ts` - 类型定义

## 测试场景

### 场景 1：触发澄清

**输入**："查询一个月的销售数据"（在银行业务数据库中）

**预期**：
- Agent 分析后展示澄清卡片
- 包含 2-3 个问题（如"销售数据指什么业务？"、"一个月指哪个时间段？"）
- 输入框 placeholder 变为"请回答澄清问题..."
- 输入框可用（不禁用）

### 场景 2：回复澄清

**输入**："账户交易数据，最近一个月，总金额和交易笔数"

**预期**：
- 澄清卡片标记为已回复（淡化显示）
- Agent 继续执行，生成 SQL 并返回结果
- 最终显示自然语言回答 + SQL + 结果表格 + 图表
- 输入框恢复默认状态

### 场景 3：刷新页面

**操作**：刷新页面后重新进入会话

**预期**：
- 澄清消息正确显示（带澄清卡片）
- 如果澄清尚未回复，输入框仍为澄清状态
- 如果已回复，澄清卡片显示为已回复状态

## 相关 Bug 修复

在实现澄清功能的同时，修复了 JSON 序列化导致 SQL 执行失败的问题：

- **问题**：沙盒执行器返回的 datetime、Decimal 等类型无法被 `json.dumps` 序列化，导致 SQL 执行报错
- **影响**：probe_min_max 等探查工具失败，减少了 LLM 可用于决策的信息，可能增加不必要的澄清
- **修复**：在沙盒执行器和通用执行器中，将非 JSON 原生类型转换为基本类型（datetime→ISO 字符串，Decimal→float 等）

修复文件：
- `sandbox-image/executor.py` - 沙盒内 SQL 执行结果序列化
- `nl2sql/executor/generic_executor.py` - 通用执行器结果转换
- `app/services/session_service.py` - 消息结果序列化兜底
