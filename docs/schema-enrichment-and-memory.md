# Schema 信息增肥 + 用户纠错记忆系统

## 概述

AskSql 的两个核心增强特性：

1. **Schema 信息增肥**：自动探测数据源，为表和列补充业务元数据（行数、样例数据、NULL 率、枚举值、Top 值等），让 LLM 生成 SQL 时理解更准确。
2. **用户纠错记忆**：从用户对话中自动检测纠错/补充，沉淀为长期记忆，下次查询时自动注入 Schema Context，持续提升 SQL 准确率。

---

## 一、Schema 信息增肥

### 增肥的数据

**表级增肥字段：**

| 字段 | 说明 | 来源 |
|------|------|------|
| `aliases` | 表别名（如 orders 表又名 order_table、交易表） | YAML 配置 |
| `business_domain` | 业务域（交易域、用户域等） | YAML 配置 |
| `row_count` | 表行数 | 自动探测 |
| `common_dimensions` | 常用维度列名列表 | YAML + 推断 |
| `common_metrics` | 常用指标（{name, expression}） | YAML + 推断 |
| `sample_rows` | 样例数据（前 N 行） | 自动探测 |
| `update_frequency` | 更新频率描述 | YAML 配置 |

**列级增肥字段：**

| 字段 | 说明 | 来源 |
|------|------|------|
| `business_name` | 业务名称（如 total_amount → 订单总额） | YAML 配置 |
| `semantic_type` | 语义类型（id/amount/category/timestamp 等） | YAML + 推断 |
| `enum_values` | 枚举值列表 | YAML 配置 |
| `distinct_count` | 去重计数 | 自动探测 |
| `top_values` | Top 值列表（{value, count, ratio}） | 自动探测 |
| `value_min` / `value_max` | 值范围（数值/时间列） | 自动探测 |
| `null_count` / `null_rate` | NULL 数量/比例 | 自动探测 |
| `calc_formula` | 计算公式 | YAML 配置 |

### 自动探测

新增/导入数据源后，系统自动触发异步探测：

- 表行数统计
- 样例数据采样（默认 5 行）
- NULL 率统计
- 数值/时间列的值范围
- 类别列的 Top 值（高基数列跳过）
- 大表降级（超过 100 万行时跳过部分统计）

探测结果自动写回 Schema YAML 文件。

### API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/schema/profile/{datasource_id}` | POST | 手动触发探测 |
| `/api/schema/profile/{datasource_id}/status` | GET | 获取探测状态 |
| `/api/schema/{datasource_id}/tables` | GET | 获取表列表（含增肥数据） |
| `/api/schema/{datasource_id}/table/{table_name}` | GET | 获取表详情（含增肥数据） |

### Schema Context 格式

增肥后的 Schema Context 示例：

```
=== 表: orders（别名: order_table, 交易表） ===
描述: 订单主表
业务域: 交易域
数据量级: 约 125,000 行
常用维度: status, created_date, channel
常用指标: GMV=sum(total_amount), order_count=count(*)
更新频率: 每日凌晨更新

列（共 5 列）:
  · order_id: VARCHAR(32) 订单编号 [id] → 非空 100.0%
  · total_amount: DECIMAL(10,2) 订单总额 [amount] → 范围: 0.01 ~ 99999.99, 非空 99.5%
  · status: VARCHAR(16) 订单状态 [category] → 枚举: pending, paid, shipped, done, cancelled, 5 个值, Top 3: paid(52%), done(28%), cancelled(10%), 非空 100.0%
  · created_at: DATETIME 创建时间 [timestamp] → 范围: 2023-01-01 ~ 2026-08-24, 非空 100.0%
  · discounted_amount: DECIMAL(10,2) 实付金额 [amount] → 范围: 0.0 ~ 99999.99, 非空 97.7% [口径: total_amount * (1 - discount_rate)]

样例数据（前 3 行）:
  order_id | total_amount | status
  ---------+--------------+--------
  1001     | 99.9         | paid
  1002     | 199.0        | pending
  1003     | 50.0         | done
```

---

## 二、用户纠错记忆系统

### 记忆类型

| 类型 | 说明 | 注入位置 |
|------|------|----------|
| `column_description` | 列的业务含义补充 | 对应列行之后 |
| `table_description` | 表的业务范围补充 | 表描述行之后 |
| `metric_definition` | 业务指标计算口径 | 顶部「业务术语说明」块 |
| `term_mapping` | 业务术语映射 | 顶部「业务术语说明」块 |
| `join_hint` | 表关联提示 | 对应表描述行之后 |

### 记忆来源与置信度

| 来源 | confidence | 说明 |
|------|------------|------|
| `manual_add` | 1.0 | 用户手动添加（最高优先级） |
| `user_correction_confirmed` | 0.9 | 自动检测并经用户隐式确认 |
| `user_correction` | 0.8 | 自动检测，待确认 |

### 纠错检测流程

```
用户发送消息
  │
  ├─ 关键词预筛（25+ 中英文关键词，无关键词直接跳过，节省 LLM 调用）
  │
  ├─ 长度检查（< 4 字符跳过）
  │
  └─ LLM 检测（temperature=0.0，JSON 格式输出）
       │
       ├─ 解析 JSON（4 层策略：直接解析 → markdown 提取 → 大括号提取 → 未转义引号修复）
       │
       ├─ Schema 验证（表/列/关联提示需要实体存在；术语/指标不需要）
       │
       ├─ 存储记忆（confidence=0.8, source=user_correction）
       │
       ├─ 加入待确认队列
       │
       └─ 下一轮 summarize 节点隐式确认 → confidence 提升到 0.9
```

### 关键词预筛

纠错关键词（中英文，共 25+）：
- 中文：不对、不是、错了、纠正、补充、说明、解释一下、其实、应该是、指的是、实际上、搞错了、更正、注意、提醒你、告诉你、不是的、不对的、说错了、讲错了、不对哦
- 英文：no, not, wrong, actually, correction

### 记忆召回

根据用户查询和相关表，从记忆库中召回最相关的记忆：

1. **表级记忆**：精确匹配表名
2. **列级记忆**：通过表名前缀匹配（表名下所有列记忆）
3. **术语映射**：关键词匹配（术语名出现在查询中）
4. **指标定义**：关键词匹配（指标名出现在查询中）

排序规则：confidence 降序 → access_count 降序 → created_at 降序
最多返回 10 条。

### 重新纠错覆盖

用户对同一实体再次纠错时：
- 自动纠错产生的记忆：**覆盖更新**（内容、confidence 重置为 0.8）
- 手动添加的记忆：**保留并存**（手动添加优先级更高，不被自动纠错覆盖）

### API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/memories` | GET | 记忆列表（支持类型筛选、搜索、分页） |
| `/api/memories` | POST | 手动添加记忆（confidence=1.0, source=manual_add） |
| `/api/memories/{id}` | GET | 获取单条记忆 |
| `/api/memories/{id}` | PUT | 编辑记忆 |
| `/api/memories/{id}` | DELETE | 删除记忆（软删除，is_active=0） |

### 前端交互

1. **记忆管理页面**：Schema 面板的「记忆」标签页，可查看/筛选/搜索/编辑/删除/手动添加记忆。
2. **实时提示**：纠错检测成功后，聊天窗口底部弹出 Toast 提示「已记下：xxx」，4 秒后自动消失。
3. **隐式确认**：下一轮 AI 回复末尾自然追加确认语句：「另外，我记下了：xxx。以后我会注意这些区别 👌」。

---

## 三、数据模型

### schema_memories 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR(32) | 主键（mem_xxx） |
| `datasource_id` | VARCHAR(32) | 数据源 ID |
| `memory_type` | VARCHAR(32) | 记忆类型 |
| `entity_type` | VARCHAR(16) | 实体类型（column/table/metric/term） |
| `entity_name` | VARCHAR(256) | 实体名称 |
| `content` | TEXT | 记忆内容 |
| `raw_content` | TEXT | 原始用户输入 |
| `source` | VARCHAR(32) | 来源（manual_add/user_correction/user_correction_confirmed） |
| `source_session_id` | VARCHAR(32) | 来源会话 ID |
| `source_message_id` | VARCHAR(32) | 来源消息 ID |
| `confidence` | FLOAT | 置信度（0.0-1.0） |
| `access_count` | INT | 访问次数（用于排序） |
| `is_active` | TINYINT | 是否有效（软删除） |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

索引：`datasource_id`、`(entity_type, entity_name)`、`is_active`

---

## 四、性能与安全

### 性能优化

- **关键词预筛**：无纠错关键词的消息不调用 LLM，节省 token
- **异步检测**：纠错检测在后台线程运行，不阻塞主查询流程
- **大表降级**：超过 100 万行的表跳过 Top 值统计
- **高基数跳过**：distinct_count > 100 的列跳过 Top 值统计
- **Fail-closed**：检测失败不影响主流程，静默降级为非纠错

### 安全考虑

- 纠错检测只从用户消息中提取 schema 业务知识，不执行任何 SQL
- 记忆只作为 LLM prompt 的补充，不影响原始 schema 定义
- 用户可在管理页面随时编辑/删除记忆
- 置信度机制：自动检测的记忆初始置信度较低，经确认后提升

---

## 五、测试覆盖

测试覆盖共 **139+ 个用例**：

| 模块 | 测试数 | 说明 |
|------|--------|------|
| Schema 模型 | 10 | 扩展字段、默认值、profiling 配置 |
| SchemaProfiler | 9 | 行数、样例、NULL 率、范围、Top 值、大表降级、高基数跳过、YAML 往返 |
| Profiling Service | 4 | 异步状态管理 |
| Schema Context | 16 | 列格式化、表上下文、紧凑模式、记忆注入 |
| 纠错检测 | 48 | 关键词、JSON 解析/修复、schema 验证、端到端 fake prompt |
| MemoryService | 41 | CRUD、召回、排名、upsert、确认、access_count |
| 集成测试 | 35 | 完整生命周期、YAML 往返、排名、隔离性 |

---

## 六、相关文件

### 核心库
- `backend/nl2sql/schema/models.py` — Table/Column 扩展模型
- `backend/nl2sql/schema/profiler.py` — SchemaProfiler 自动探测
- `backend/nl2sql/schema/loader.py` — YAML 加载器
- `backend/nl2sql/agent/nodes/_schema_context.py` — Schema Context 构建 + 记忆注入

### 应用服务
- `backend/app/services/profiling_service.py` — 异步探测服务
- `backend/app/services/memory_service.py` — 记忆服务（CRUD + 召回）
- `backend/app/services/correction_detector.py` — 纠错检测服务
- `backend/app/services/chat_service.py` — 对话集成（异步检测 + 待确认队列）

### Agent 节点
- `backend/nl2sql/agent/nodes/generate.py` — SQL 生成节点（记忆召回 + 注入）
- `backend/nl2sql/agent/nodes/summarize.py` — 总结节点（隐式确认）

### API
- `backend/app/api/schema.py` — Schema + 探测 API
- `backend/app/api/memories.py` — 记忆管理 API

### 前端
- `frontend/src/components/schema/SchemaPanel.tsx` — Schema 面板（含增肥数据展示）
- `frontend/src/components/schema/MemoryPanel.tsx` — 记忆管理面板
- `frontend/src/components/chat/MemorySavedToast.tsx` — 纠错保存提示
