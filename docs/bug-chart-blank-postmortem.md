# 图表空白问题复盘（面试题版）

> 一句话总结：三个独立 Bug 叠加在同一个现象上（图表空白），每修一个只能看到下一个，导致反复排查。
>
> 标签：`LangGraph` · `React` · `Recharts` · `getattr vs dict` · `slice(null)` · `interval=preserveEnd`

---

## 一、问题现象

用户反馈"图表是空的"：

- ✅ 图表卡片渲染了（标题、边框、玻璃质感背景都有）
- ✅ 网格线能看到（虚线）
- ❌ 没有折线、柱状等数据图形
- ❌ 没有坐标轴标签 / 只有最右侧一个标签
- ❌ 没有数据点

**第一反应**：LLM 生成的图表字段和实际列名不匹配 → 实际是错的。

---

## 二、为什么改了多次都没修好？

**核心原因：3 个独立 Bug 叠加，呈现同一个现象"图表空白"。每修好一个，下一个以相似表象出现，让人以为"没修好"。**

```
用户看到：图表空白
    │
    ├─→ Bug 1：viz_ready 事件发不出来（后端事件层）
    │       ↓ 修复后……
    ├─→ Bug 2：rows.slice(0, null) 返回空数组（前端数据层）
    │       ↓ 修复后……
    └─→ Bug 3：X 轴标签被自动省略（前端展示层）
```

每一层的 Bug 都让人以为是"自己正在排查的那个问题"，实际上修好了一个，马上又撞上另一个。

---

## 三、Bug 1：`getattr` 在 dict state 上静默失效

### 位置

后端 11 个 agent 节点文件（`nodes/*.py`）的 `_send_event` 函数，外加 `execute.py` 和 `sql_tool.py` 的 `_get_executor`。

### 代码

```python
# 修复前
def _send_event(state, event_type, data=None):
    callback = getattr(state, "event_callback", None)  # ❌
    if callback is not None:
        callback(event_type, data or {})
```

### 为什么是 Bug

LangGraph 运行时，state 经过 `model_dump()` 后是 **dict**，不再是 Pydantic 模型。

```python
state = {"event_callback": my_func, "sql": "SELECT ..."}

getattr(state, "event_callback", None)
# → 返回 None！因为 dict 的属性只有 keys/items 等，
#    字典的 key 不会被 getattr 读取到。

state.get("event_callback")
# → 返回 my_func，这才是正确的。
```

### 为什么难发现

| 原因 | 说明 |
|------|------|
| **测试不覆盖** | 单元测试直接传 Pydantic 模型，`getattr` 能拿到值，测试全绿 |
| **静默失败** | 不报错，不抛异常，只是事件不发。系统照常运行，只是前端看不到进度 |
| **现象模糊** | 前端表现为"没有思考时间线、没有图表、SQL 也不显示"，容易归因为 SSE 连接问题 |

### 验证方法

```python
# 一句话验证
state_dict = {"event_callback": lambda *a: print("called")}
print(getattr(state_dict, "event_callback", "NOT_FOUND"))  # 输出 "NOT_FOUND"
print(state_dict.get("event_callback"))                   # 输出函数对象
```

### 修复

```python
def _send_event(state: dict | Any, event_type: str, data: dict | None = None) -> None:
    if isinstance(state, dict):
        callback = state.get("event_callback")
    else:
        callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass
```

**通用模式**：LangGraph 节点函数中，所有通过 `extra_state` 注入的运行时字段（`event_callback`、`datasource_executors`、`step_logger` 等），都不能用 `getattr`。

### 面试追问

> Q: 为什么 LangGraph 要把 state 转成 dict？用 Pydantic model 不行吗？

A: LangGraph 内部用 `Pregel` 引擎做状态机流转，每个节点输出一个 dict 表示"要更新的 state 字段"，然后 LangGraph 内部做 merge。Pydantic model 是"完整对象"，不适合做增量更新的中间表示。所以运行时是 dict，只有入口和出口才是模型实例。

---

## 四、Bug 2：`slice(0, null)` 返回空数组

### 位置

前端 `chartUtils.ts` 的 `rowsToObjects` 函数。

### 代码

```typescript
// 修复前
export function rowsToObjects(columns: string[], rows: unknown[][], limit?: number) {
  const data = limit !== undefined ? rows.slice(0, limit) : rows
  // ...
}
```

### 触发路径

1. 后端 `_validate_viz_spec` 中 `limit` 默认值是 `null`
2. JSON 序列化后传到前端，`chart.limit = null`
3. `limit !== undefined` → `null !== undefined` → **true**
4. 执行 `rows.slice(0, null)`

### 关键知识点：`slice` 的参数转换

`Array.prototype.slice(start, end)` 的 `end` 参数：

| end 的值 | 行为 | 结果 (3 行数据) |
|----------|------|----------------|
| `undefined` | 一直切到末尾 | `[1,2,3]` ✅ |
| `null` | 被强制转换为 `0` | `[]` ❌ |
| `0` | 从开头切到开头 | `[]` |
| `3` | 切前 3 个 | `[1,2,3]` |

> 很多人以为 `null` 和 `undefined` 行为一样，实际上 `slice` 内部用 `ToInteger(null) = 0`。

### 为什么难发现

| 原因 | 说明 |
|------|------|
| **直觉偏差** | 看到 `!== undefined` 觉得没问题，忽略了 `null` 的情况 |
| **不报错** | 返回空数组是合法行为，Recharts 正常渲染空图 |
| **误导性表象** | 只看到网格线、没有数据，容易怀疑"字段没匹配上" |

### 验证方法

```javascript
// 浏览器控制台一句话验证
console.log([1,2,3].slice(0, null));     // []  ← 坑！
console.log([1,2,3].slice(0, undefined)); // [1,2,3]
```

### 修复

```typescript
const data = limit != null && limit > 0 ? rows.slice(0, limit) : rows
```

- `!= null` 同时排除 `null` 和 `undefined`
- `> 0` 排除 0 和负数等无意义值

### 面试追问

> Q: 为什么后端 limit 默认值是 null 而不是 undefined？

A: Python 的 `dict.get("key")` 找不到时默认返回 `None`，JSON 序列化后 `None` → `null`。前后端语言差异导致的类型不一致是常见坑点。

> Q: TypeScript 里 `limit?: number` 为什么会是 null？

A: `?:` 只意味着"可以不传 / 是 undefined"，但运行时数据来自 JSON API，null 可以畅通无阻地传进来。TypeScript 不做运行时校验。这也是为什么大型项目会用 Zod / io-ts 做运行时类型守卫。

---

## 五、Bug 3：X 轴标签被自动省略

### 位置

`LineChartView.tsx`、`BarChartView.tsx`、`AreaChartView.tsx` 的 `<XAxis>` 组件。

### 代码

```tsx
// 修复前
<XAxis
  dataKey={xField}
  tick={{ fontSize: 11, fill: '#94a3b8' }}
  tickLine={false}
  axisLine={{ stroke: '#e2e8f0' }}
/>
```

### 问题

Recharts 的 XAxis 默认 `interval="preserveEnd"`——"保证最后一个标签可见，其他标签根据空间自动省略"。

当 X 轴值是 `2024-06-01T00:00:00` 这种长字符串时：
- 3 个标签每个约 120px 宽
- 图表宽度可能只有 300px
- Recharts 计算后认为只能放下 1 个
- 只保留最后一个（`preserveEnd`）

用户看到的就是"X 轴只有一个数据 / 没有数据"。

### 为什么难发现

| 原因 | 说明 |
|------|------|
| **不是 Bug，是特性** | 这是 Recharts 的默认行为，文档里有写，容易忽略 |
| **数据是对的** | 折线其实在那里（如果 Bug 2 已修），只是标签不显示 |
| **容易误判** | 会让人以为"数据没传进去"或"X 轴 dataKey 配错了" |

### 验证方法

在浏览器 DevTools 里看 SVG DOM：

```javascript
// 看 X 轴有多少个 tick
document.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick')
// 如果数量 < 数据行数，说明被省略了
```

### 修复

```tsx
<XAxis
  dataKey={xField}
  interval={0}          // 强制显示所有标签
  tickFormatter={formatX} // 同时格式化标签，让它更短更可读
  ...
/>
```

配合日期格式化（`2024-06-01T00:00:00` → `2024-06`），标签变短后也更容易放下。

---

## 六、日期格式化的附加坑

### 问题

`new Date('2024-06-01')` 按 **UTC 时间** 解析，在东八区显示成 `2024-06-01 08:00:00`——纯日期莫名多了 8 点。

### 原因

ES5 之后，`YYYY-MM-DD` 格式的字符串被规定为 UTC 时间解析，而 `YYYY-MM-DD HH:mm:ss` 格式按本地时间解析。**格式不同，时区不同**。

### 修复

```typescript
// 纯日期用本地时间构造
const match = str.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/)
if (match) {
  date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  )
} else {
  date = new Date(str)
}
```

---

## 七、排查方法论

遇到"图表空白"这类多因素叠加问题，推荐的排查顺序：

### 第一步：确认数据链路（自上而下）

```
后端 viz_ready 事件？
    → 前端 SSE 收到了吗？（Network 面板 / SSE 事件监听）
        → ChartGrid 组件收到 props 了吗？（React DevTools / console.log）
            → rowsToObjects 转换后 data 有值吗？
                → Recharts 收到的 data 对吗？
                    → xField / yFields 解析正确吗？
                        → tick 被省略了吗？
```

**每一层都确认"数据确实在这里且是对的"**，再往下走。不要跳步。

### 第二步：区分"没数据"和"数据没显示"

- DOM 里有 `.recharts-line path` 吗？有 = 数据已渲染，只是样式/颜色问题
- SVG 里有 XAxis/YAxis 的 tick 元素吗？有但看不见 = 被省略/隐藏
- 完全没有图形 = data 是空的

### 第三步：警惕"静默失效"

以下都是**不报错但功能失效**的模式，排查优先级高：

| 模式 | 例子 |
|------|------|
| `getattr(dict, key)` 返回默认值 | Bug 1 |
| `slice(0, null)` 返回空数组 | Bug 2 |
| `interval="preserveEnd"` 省略标签 | Bug 3 |
| `Array.includes` 区分大小写 | 字段匹配失败 |
| 时区差异导致日期偏移 | 日期格式化 |

---

## 八、修改文件清单

### 后端（事件系统修复 · 13 个文件）

- `nl2sql/agent/nodes/_step_utils.py`
- `nl2sql/agent/nodes/intent.py`
- `nl2sql/agent/nodes/generate.py`
- `nl2sql/agent/nodes/execute.py`
- `nl2sql/agent/nodes/reflect.py`
- `nl2sql/agent/nodes/visualize.py`
- `nl2sql/agent/nodes/summarize.py`
- `nl2sql/agent/nodes/clarify.py`
- `nl2sql/agent/nodes/rewrite.py`
- `nl2sql/agent/nodes/probe.py`
- `nl2sql/agent/nodes/connect_datasource.py`
- `nl2sql/agent/tools/sql_tool.py`
- `app/services/chat_service.py`（验证链路）

### 前端（图表修复 · 6 个文件）

| 文件 | 修改 |
|------|------|
| `src/components/chart/chartUtils.ts` | 修复 `rowsToObjects` limit 判断 + 新增 `formatDateTick` / `formatNumberTick` / `smartFormatTick` / `isDateTimeValue` |
| `src/components/chart/LineChartView.tsx` | `interval={0}` + `tickFormatter` + Y 轴加宽 |
| `src/components/chart/BarChartView.tsx` | 同上 |
| `src/components/chart/AreaChartView.tsx` | 同上 |
| `src/lib/types.ts` | `ChartSpec` 增加 `x_format` / `y_format` 字段 |
| `src/hooks/useSSE.ts` | 补充缺失的 SSE 事件类型注册 |

### 后端（可视化 Prompt 优化 · 1 个文件）

- `nl2sql/agent/nodes/visualize.py` — Prompt 增加 `x_format` / `y_format` 说明

---

## 九、面试自测题

1. **LangGraph 中 state 是 dict 还是 Pydantic 模型？为什么？在节点里如何安全地获取动态注入的字段？**
2. **`[1,2,3].slice(0, null)` 返回什么？为什么？`undefined` 呢？**
3. **Recharts X 轴默认的 interval 是什么行为？什么时候会导致标签缺失？**
4. **`new Date('2024-06-01')` 和 `new Date('2024-06-01 00:00:00')` 在东八区有什么区别？**
5. **TypeScript 的 `?:` 可选类型能防止 null 吗？为什么？**
6. **如果图表是空白的，你的排查顺序是什么？说 5 个步骤。**
7. **为什么单元测试全过但线上出问题？这个案例给你什么启示？**

---

## 十、一句话总结

> "图表空白"是一个经典的"多层 Bug 叠加"问题——后端事件、数据转换、前端展示，每一层各有一个 Bug，全部表现为"图表不显示"。
> 核心教训是：**排查时不要想当然，一层一层验证数据在哪里丢的；对"静默失效"模式保持高度警惕。**
