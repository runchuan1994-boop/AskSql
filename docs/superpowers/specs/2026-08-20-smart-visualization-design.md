# Smart Visualization（智能可视化）设计文档

> **功能：** 在对话中，由 AI Agent 根据用户查询语义、SQL 结构和数据特征，自动决定最佳数据展示形式（折线图/柱状图/饼图/表格/指标卡等），并在前端动态渲染。支持大数据量分页。

---

## 1. 背景与目标

### 1.1 现状

当前 NL2SQL Agent 对话的输出形式：
- 文字回答（LLM 总结）
- SQL 代码块
- 纯表格展示查询结果（最多 100 行截断）

问题：
- 表格是唯一的数据展示形式，不够直观
- 趋势、占比、对比等数据关系需要用户自己从表格里"读"出来
- 大数据量下前端截断，无法浏览完整数据

### 1.2 目标

- AI 自动选择最合适的图表类型（折线/柱状/饼图/面积/指标卡/表格）
- AI 可以决定输出多个图表组合
- 图表配置由 LLM 生成结构化 JSON，前端动态渲染
- 表格支持服务端分页，大数据量可浏览
- 不显著增加延迟（一次额外的 LLM 调用）

---

## 2. 架构设计

### 2.1 Agent 图变更

在现有 LangGraph 图中，`execute` 节点之后、`summarize` 节点之前，新增 `visualize` 节点：

```
intent → probe → clarify → generate → execute → visualize → summarize → reflect (循环)
                                                        ↑
                                                  新节点位置
```

**为什么是一个 Node 而不是独立 Agent？**
- 输入确定（SQL + 执行结果 + 用户查询）
- 输出确定（图表配置 JSON）
- 不需要工具调用、不需要多步推理
- 一次 LLM 调用完成，延迟可控

### 2.2 节点职责

**visualize_node：**
- 输入：`user_query`, `sql`, `execution_result`
- 调用 LLM，让其分析数据并输出图表配置 JSON
- 解析并校验 JSON 结构
- 输出：`viz_spec`（VizSpec 对象）

**summarize_node 调整：**
- 输入中增加 `viz_spec`
- 系统提示词中增加："如果有图表，回答中可以适当引导用户看图"
- 输出的 final_result 事件中携带 `viz` 字段

### 2.3 数据流

```
1. POST /api/chat  → 启动 Agent
2. Agent 执行 SQL → execution_result
3. visualize_node → LLM 生成 VizSpec
   → SSE 推送 viz_ready 事件（前端立即开始渲染图表）
4. summarize_node → 生成文字回答
   → SSE 推送 final_result 事件（含 answer + viz）
5. 前端表格数据按需分页加载
   → GET /api/chat/{session_id}/result?page=1&page_size=100
```

---

## 3. 数据模型

### 3.1 VizSpec（可视化规范）

```typescript
// 单个图表配置
interface ChartSpec {
  id: string                    // 唯一标识（前端用）
  type: ChartType               // 图表类型
  title: string                 // 图表标题
  description?: string          // 可选：图表说明文字

  // 数据映射
  x_field?: string              // X 轴字段名（折线/柱状/面积用）
  y_field?: string              // Y 轴字段名（单值时）
  y_fields?: string[]           // Y 轴字段列表（多系列时）
  category_field?: string       // 分类字段（饼图/堆叠图的图例维度）
  value_field?: string          // 数值字段（饼图用）

  // 展示控制
  sort?: 'asc' | 'desc' | null  // 是否排序
  limit?: number                // 展示前 N 条（Top N）
  stacked?: boolean             // 是否堆叠（柱状/面积图）

  // 扩展配置
  config?: Record<string, any>  // 额外的图表配置（颜色、标签等）
}

type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'metric' | 'table'

// 完整的可视化规范
interface VizSpec {
  charts: ChartSpec[]           // 图表列表，0-N 个
  data_preview?: DataPreview    // 数据预览（前 N 行，供图表初始渲染用）
}

interface DataPreview {
  columns: string[]
  rows: unknown[][]
  total_rows: number
  has_more: boolean
}
```

### 3.2 后端消息结构扩展

`messages` 表的 `result_json` 中增加 `viz` 字段：
```python
# add_message 时，result dict 里包含 viz
result_dict = {
    "columns": ...,
    "rows": [...],       # 只存前 100 行预览
    "row_count": ...,
    "success": ...,
    "viz": {              # 新增
        "charts": [...],
    }
}
```

---

## 4. 后端实现

### 4.1 新增文件

- `backend/nl2sql/agent/nodes/visualize.py` — visualize 节点实现
- `backend/nl2sql/agent/visualization/` — 可视化相关工具（可选，如果逻辑复杂）

### 4.2 修改文件

- `backend/nl2sql/agent/graph.py` — 在图中加入 visualize 节点
- `backend/nl2sql/agent/nodes/summarize.py` — 调整 prompt，感知图表
- `backend/nl2sql/agent/state.py` — 增加 viz_spec 字段
- `backend/app/services/chat_service.py` — 透传 viz 数据，新增分页接口
- `backend/app/api/chat.py` — 新增分页查询结果的端点

### 4.3 Visualize Node Prompt 设计

```
你是一位数据可视化专家。根据用户的问题、SQL 查询和执行结果，
选择最合适的数据展示形式。

支持的图表类型：
- line: 折线图 — 用于时间趋势、变化率
- bar: 柱状图 — 用于分类对比、排名
- pie: 饼图 — 用于占比分布（类别不超过 8 个时使用）
- area: 面积图 — 用于累计趋势、堆叠展示
- metric: 指标卡 — 用于单个核心数值
- table: 表格 — 用于明细数据、多列复杂数据

判断规则：
1. 时间相关 + 数值 → line 或 area
2. 分类 + 数值对比 → bar
3. 占比/分布 + 类别少 → pie
4. 单个数字结果 → metric
5. 明细/列表/多列数据 → table
6. 可以输出多个图表，比如"趋势图 + 数据表格"

输出格式（严格 JSON，不要其他文字）：
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
```

### 4.4 结果分页 API

新增端点：
```
GET /api/chat/messages/{message_id}/result?page=1&page_size=100
```

返回：
```json
{
  "columns": ["date", "amount", "category"],
  "rows": [...],
  "page": 1,
  "page_size": 100,
  "total": 1234,
  "has_more": true
}
```

**实现思路：**
- Agent 执行结果完整保存在内存/缓存中（按 message_id 索引）
- 分页接口从缓存中切片返回
- 或者：重新执行分页 SQL（LIMIT/OFFSET）
- V1 方案：Agent 执行的全量结果存在内存缓存（默认 TTL 30 分钟），分页从缓存读

---

## 5. 前端实现

### 5.1 新增依赖

- `recharts` — 图表库

### 5.2 新增组件

```
frontend/src/components/chart/
├── ChartRenderer.tsx      # 图表渲染器（根据 type 动态选择）
├── LineChartView.tsx      # 折线图
├── BarChartView.tsx       # 柱状图
├── PieChartView.tsx       # 饼图
├── AreaChartView.tsx      # 面积图
├── MetricCard.tsx         # 指标卡片
└── chartUtils.ts          # 图表工具函数（数据转换、颜色等）
```

### 5.3 组件关系

```
ChatMessage
  ├── 文字内容
  ├── SqlDisplay
  ├── [新增] ChartGrid          # 图表网格容器
  │     └── ChartRenderer × N   # 每个图表一个渲染器
  │           └── LineChartView / BarChartView / ...
  └── ResultTable (可折叠，支持分页)
```

### 5.4 分页改造

`ResultTable` 组件：
- 从全量数据渲染 → 分页渲染
- 底部加分页控件（上一页/下一页/页码/每页条数）
- 翻页时调用分页 API 获取数据
- 第一页数据从 message.result 直接拿，后续页懒加载

### 5.5 样式设计原则（高级感）

- **配色**：统一的品牌色板，图表系列色协调不刺眼
- **留白**：图表周围充足 padding，标题和图表有呼吸感
- **字体**：标题用 medium 字重，轴标签用小号轻量字体
- **动效**：图表入场有淡入动画，数据切换有平滑过渡
- **交互**：hover 显示 tooltip，支持图例点击切换系列显隐
- **容器**：圆角卡片，微妙阴影，和现有 UI 风格统一

### 5.6 类型定义扩展

`types.ts` 中增加：
```typescript
export type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'metric' | 'table'

export interface ChartSpec {
  id: string
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

// Message 扩展
export interface Message {
  // ... 现有字段
  viz?: VizSpec | null
}
```

---

## 6. SSE 事件扩展

新增事件类型：

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `viz_ready` | visualize_node 完成后 | `{ charts: ChartSpec[] }` |

现有 `final_result` 事件增加 `viz` 字段。

---

## 7. 错误处理与降级策略

### 7.1 LLM 输出解析失败
- JSON 解析出错时，降级为"仅表格展示"
- 记录日志，不影响主流程

### 7.2 图表渲染失败
- 某个图表类型不支持或数据格式不对时，降级为表格展示该部分数据
- 前端 try/catch 包裹，失败时显示"图表渲染失败，已切换为表格"

### 7.3 大数据量
- 执行结果 > 1000 行时，图表只用前 1000 行渲染
- 前端提示"数据量较大，图表展示前 1000 行"
- 表格走分页，可浏览全量

### 7.4 AI 选图不合理
- 每个图表右上角有"切换图表类型"的下拉菜单
- 用户可以手动切换到其他类型，前端自动适配

---

## 8. 测试策略

### 8.1 后端测试
- `test_visualize_node.py` — 测试可视化节点的 JSON 解析、校验、降级逻辑
- Mock LLM 返回各种合法/非法 JSON，验证解析容错

### 8.2 前端测试
- 各图表组件的 snapshot 测试
- ChartRenderer 的 type 分发逻辑测试
- 分页逻辑测试

---

## 9. 实施顺序

1. **后端：visualize_node** — 节点实现 + 图接入 + SSE 事件
2. **后端：结果缓存 + 分页 API** — 全量结果缓存 + 分页查询端点
3. **前端：图表组件库** — Recharts 接入 + 各图表组件 + ChartRenderer
4. **前端：图表集成到聊天** — ChatMessage 中增加图表区域
5. **前端：表格分页改造** — ResultTable 分页 + 分页 API 对接
6. **联调 + 样式优化** — 端到端联调，打磨视觉效果

---

## 10. 后续可扩展方向

- 更多图表类型：散点图、热力图、漏斗图、双轴图
- 图表交互：点击图表下钻、自然语言调整图表样式
- 图表导出：PNG/SVG 导出
- 自定义配色主题
- AI 自动生成多图表看板（需要独立 Agent）
