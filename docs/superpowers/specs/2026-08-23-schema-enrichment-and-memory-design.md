# Schema 信息增肥 + 用户纠错记忆系统 — 设计文档

**日期**: 2026-08-23
**状态**: 待评审
**版本**: v1.0

---

## 背景与目标

当前系统在少表场景（< 20 张表）下，Schema 信息单薄导致 LLM 对数据理解不深，SQL 生成准确率有提升空间。同时，用户在对话中发现错误并纠正后，这些知识无法沉淀复用，下次还会犯同样的错。

**目标**：
1. **Schema 增肥**：丰富传给 LLM 的 schema 上下文信息，让 LLM 更懂数据，提升 SQL 生成准确率
2. **用户纠错记忆**：从用户对话中自动提取纠错/补充信息，沉淀为长期记忆，下次自动生效
3. **不引入重型组件**：在现有架构内实现，不需要向量数据库等新基础设施

---

## 一、Schema 信息增肥

### 1.1 数据模型扩展

在 `nl2sql/schema/models.py` 的 `Table` 和 `Column` 模型上增加字段。

**Table 扩展：**

| 字段 | 类型 | 默认值 | 来源 | 说明 |
|------|------|--------|------|------|
| `aliases` | `list[str]` | `[]` | YAML | 业务别名列表 |
| `business_domain` | `str` | `""` | YAML | 所属业务域 |
| `row_count` | `int \| None` | `None` | 自动探测 | 数据行数 |
| `common_dimensions` | `list[str]` | `[]` | YAML + 推断 | 常用维度列名 |
| `common_metrics` | `list[dict]` | `[]` | YAML + 推断 | 常用指标，每项包含 name 和 expression |
| `sample_rows` | `list[dict]` | `[]` | 自动探测 | 样例数据（前 3-5 行，列名→值） |
| `update_frequency` | `str` | `""` | YAML | 更新频率描述 |

**Column 扩展：**

| 字段 | 类型 | 默认值 | 来源 | 说明 |
|------|------|--------|------|------|
| `business_name` | `str` | `""` | YAML | 业务名称 |
| `distinct_count` | `int \| None` | `None` | 自动探测 | 去重值数量 |
| `top_values` | `list[dict]` | `[]` | 自动探测 | 高频值及占比，每项 {value, count, ratio} |
| `value_min` | `str \| None` | `None` | 自动探测 | 最小值（数值/时间/字符串通用） |
| `value_max` | `str \| None` | `None` | 自动探测 | 最大值 |
| `null_count` | `int \| None` | `None` | 自动探测 | NULL 行数 |
| `null_rate` | `float \| None` | `None` | 自动探测 | NULL 率（0.0 ~ 1.0） |
| `calc_formula` | `str` | `""` | YAML | 计算口径说明（衍生字段） |

**注意**：所有新增字段都有合理默认值，向后兼容现有 YAML 文件。

### 1.2 YAML Schema 格式扩展

现有 YAML 格式保持兼容，新增可选字段。示例：

```yaml
tables:
  - name: orders
    description: 订单表
    aliases: [交易表, 下单表]            # 新增
    business_domain: 交易域               # 新增
    update_frequency: 实时                # 新增
    common_dimensions: [user_id, channel, created_at]  # 新增
    common_metrics:                       # 新增
      - name: GMV
        expression: SUM(total_amount)
      - name: 订单量
        expression: COUNT(*)
    columns:
      - name: order_id
        type: BIGINT
        description: 订单ID
        is_primary_key: true
      - name: total_amount
        type: DECIMAL(10,2)
        description: 订单总金额
        business_name: 商品原价            # 新增
        semantic_type: amount
      - name: status
        type: VARCHAR
        description: 订单状态
        semantic_type: category
        enum_values: [pending, paid, shipped, completed, cancelled]
      # ...
```

### 1.3 自动探测服务

新增 `SchemaProfiler` 服务（`nl2sql/schema/profiler.py`），负责从数据库中统计信息并填充到 schema 对象中。

**探测内容：**

| 项目 | SQL 方式 | 适用列类型 |
|------|---------|-----------|
| 表行数 | `SELECT COUNT(*) FROM table` | 所有表 |
| 样例数据 | `SELECT * FROM table LIMIT 5` | 所有表 |
| NULL 数/率 | `SELECT COUNT(*) - COUNT(col) FROM table` | 所有列 |
| 数值范围 | `SELECT MIN(col), MAX(col) FROM table` | 数值型、日期型 |
| 去重数量 | `SELECT COUNT(DISTINCT col) FROM table` | 类别型（低基数） |
| Top 值及占比 | `SELECT col, COUNT(*) as cnt FROM table GROUP BY col ORDER BY cnt DESC LIMIT 10` | 类别型（低基数） |

**智能判断哪些列需要深度探测：**
- `semantic_type = category` 或枚举列 → 统计 top_values + distinct_count
- `semantic_type = amount / timestamp` → 统计 value_min / value_max
- 所有列 → 统计 null_rate
- 如果 `distinct_count > 100` → 认为是高基数列，不统计 top_values（避免性能问题）

**探测执行时机：**
- 数据源连接成功后，**后台异步**执行探测
- 探测结果写入 schema YAML 文件（追加统计信息）
- 探测过程不阻塞用户使用
- 大表（>100万行）的探测做降级：只采样前 10 万行统计，或直接跳过 top_values 统计

**探测配置（可在 YAML 中关闭）：**
```yaml
profiling:
  enabled: true
  sample_row_count: 5
  max_rows_for_full_profiling: 1000000  # 超过此行数的表不做全量探测
```

### 1.4 Schema Context 输出格式

改造 `generate.py` 中的 `_build_detailed_schema_context`，输出更丰富的格式给 LLM。

**格式示例：**

```
=== 表: orders（别名: 订单表, 交易表）===
描述: 记录用户下单信息
业务域: 交易域
数据量级: 约 523,400 行
常用维度: user_id, channel, created_at
常用指标: GMV=SUM(total_amount), 订单量=COUNT(*)
更新频率: 实时

列（共 15 列）:
  · order_id: BIGINT [PK] 订单ID → 非空 100%
  · user_id: BIGINT [FK→users.id] 用户ID → 非空 100%
  · total_amount: DECIMAL(10,2) 商品原价 [amount] → 范围: 0.01 ~ 99999.99, 非空 99.5%
  · final_amount: DECIMAL(10,2) 实付金额 [amount] → 范围: 0.01 ~ 99999.99, 非空 99.5%
  · status: VARCHAR 订单状态 [category] → 5 个枚举值: paid(60%), shipped(20%), pending(15%), completed(5%), cancelled(0%)
  · channel: VARCHAR 来源渠道 [category] → 12 个枚举值, Top 3: organic(40%), paid(35%), referral(15%)
  · created_at: DATETIME 下单时间 [timestamp] → 范围: 2023-01-01 ~ 2026-08-23, 非空 100%
  ...（其余列省略，或按相关性排序）

样例数据（前 3 行）:
  order_id | user_id | total_amount | final_amount | status | channel | created_at
  10001    | 123     | 299.00       | 259.00       | paid   | organic | 2026-08-20 10:30:00
  10002    | 456     | 599.00       | 599.00       | shipped| paid    | 2026-08-20 11:15:00
  10003    | 789     | 129.00       | 99.00        | paid   | referral| 2026-08-20 12:00:00
```

**设计要点：**
- 信息分层呈现：表级信息 → 列信息 → 样例数据
- 列信息用紧凑的一行格式（类型、标记、描述、语义类型、统计信息），减少 token 占用
- 样例数据用表格形式，LLM 容易理解
- 列数 > 10 张表时，可以考虑只显示高相关列（由 SchemaMatcher 排序后取 Top 10），其余列名用省略号

### 1.5 与现有系统的集成点

| 文件 | 改动 |
|------|------|
| `nl2sql/schema/models.py` | Table/Column 模型新增字段 |
| `nl2sql/schema/loader.py` | YAML 加载逻辑兼容新字段 |
| `nl2sql/schema/profiler.py` | 🆕 新增：自动探测服务 |
| `nl2sql/agent/nodes/generate.py` | `_build_detailed_schema_context` 输出新格式 |
| `nl2sql/agent/nodes/intent.py` | `_build_schema_context` 也适度增肥（增加表别名等信息） |
| `app/services/schema_import.py` | 导入 schema 后触发异步探测 |
| `app/services/schema_service.py` | 提供探测状态查询 API |

---

## 二、用户纠错记忆系统

### 2.1 设计原则

1. **数据源级隔离**：记忆只对所属数据源生效
2. **记忆作为补充**：不覆盖原始 schema 描述，以"用户备注"形式附加，LLM 自己判断
3. **自然语言交互**：用户在对话中直接纠正，系统自动检测提取，无需专门操作
4. **隐式确认**：检测到纠错后，在回复中自然确认，不打断对话
5. **可溯源**：每条记忆记录来源（session_id、message_id、时间）

### 2.2 数据模型

新增表 `schema_memories`（在应用数据库 SQLite 中）：

```sql
CREATE TABLE schema_memories (
    id TEXT PRIMARY KEY,
    datasource_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,          -- column_description / table_description / metric_definition / term_mapping / join_hint
    entity_type TEXT,                   -- table / column / metric / term
    entity_name TEXT,                   -- 实体名称
    content TEXT NOT NULL,              -- 记忆内容（整理后的规范表述）
    raw_content TEXT,                   -- 用户原话（用于溯源和调试）
    source TEXT NOT NULL,               -- user_correction / user_question / manual_add
    source_session_id TEXT,             -- 溯源：会话 ID
    source_message_id TEXT,             -- 溯源：消息 ID
    confidence REAL DEFAULT 0.8,        -- 置信度（manual_add=1.0，自动提取=0.8）
    access_count INTEGER DEFAULT 0,     -- 被召回次数
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE INDEX idx_memories_datasource ON schema_memories(datasource_id);
CREATE INDEX idx_memories_entity ON schema_memories(datasource_id, entity_type, entity_name);
CREATE INDEX idx_memories_active ON schema_memories(datasource_id, is_active);
```

**记忆类型说明：**

| memory_type | entity_type | 说明 | 示例 content |
|-------------|-------------|------|-------------|
| `column_description` | `column` | 列的业务含义补充 | `"amount 是商品原价，不是实付金额，实付看 final_amount"` |
| `table_description` | `table` | 表的业务含义补充 | `"orders 表只存主站订单，不包含小程序订单"` |
| `metric_definition` | `metric` | 业务指标计算口径 | `"GMV = total_amount + shipping_fee - discount_amount"` |
| `term_mapping` | `term` | 业务术语映射 | `"流水 就是 GMV，即订单总金额"` |
| `join_hint` | `table` | 表关联提示 | `"orders 和 users 通过 user_id 关联，但注意游客下单时 user_id 为 NULL"` |

### 2.3 记忆服务（MemoryService）

新增 `app/services/memory_service.py`，提供以下能力：

| 方法 | 说明 |
|------|------|
| `add_memory(datasource_id, memory_type, entity_type, entity_name, content, ...)` | 添加一条记忆 |
| `get_memories_for_table(datasource_id, table_name)` | 获取某张表的所有相关记忆（表级+列级） |
| `get_memories_for_query(datasource_id, query, related_tables)` | 根据查询和相关表召回相关记忆 |
| `update_memory(memory_id, updates)` | 更新记忆 |
| `delete_memory(memory_id)` | 删除记忆（软删除，is_active=0） |
| `list_memories(datasource_id, filters)` | 列出某数据源的记忆（分页、筛选） |
| `increment_access(memory_id)` | 增加访问计数 |

**记忆召回逻辑（`get_memories_for_query`）：**

```
输入：用户查询 + 相关表列表
输出：相关记忆列表（按相关性排序）

步骤：
1. 找出相关表对应的所有记忆（表级 + 列级）
   → entity_name 在相关表名 / 相关列名中
2. 对术语型记忆（term_mapping），用关键词匹配：
   → 用户查询中包含术语的关键词
3. 合并去重，按以下优先级排序：
   a. confidence 高的在前
   b. access_count 多的在前
   c. created_at 新的在前
4. 返回 Top 10 条
```

召回先用规则匹配（表名/列名精确匹配 + 关键词匹配），表少场景下足够准确。等以后表多了再考虑向量召回。

### 2.4 纠错检测与记忆提取

**流程时机**：用户发送消息后，在正常回答的**同时**，异步检测是否为纠错。

```
用户消息到达
  │
  ├─ 主流程：正常问答（意图分析 → 生成 → 执行 → 反思 → 总结）
  │
  └─ 异步任务：纠错检测
       │
       ├─ 1. 用 LLM 判断是否为纠错/补充
       │      Prompt: 判断用户消息是否在纠正或补充数据库 schema 的业务含义...
       │      输出: { is_correction: bool, memory_type, entity_type, entity_name, content }
       │
       ├─ 2. 如果是纠错 → 提取结构化记忆
       │      → 校验 entity_name 是否真实存在（表/列是否存在）
       │      → 存入记忆库（confidence=0.8, source=user_correction）
       │      → 将记忆信息存入当前 session 的状态（待确认）
       │
       └─ 3. 不是纠错 → 什么都不做
```

**检测 Prompt 设计要点：**
- 明确什么算纠错：纠正字段含义、补充业务术语、说明计算口径、指出表的用途等
- 明确什么不算纠错：普通追问、换个维度再看看、数据本身的问题（"这个数不对"但没说为什么）
- 要求输出严格 JSON，方便解析
- 如果判断不是纠错，`is_correction = false`，其余字段为空

**检测触发条件**（先做简单的，避免每条消息都调 LLM）：
- 用户消息中包含纠错关键词时才触发检测："不对""不是""错了""纠正""补充""说明""解释一下""其实""应该是""指的是"等
- 没有这些关键词 → 直接跳过检测，省 token

### 2.5 隐式确认机制

检测到纠错并存储后，在下一轮 AI 回复中自然地加入确认语句。

**实现方式**：
- 纠错检测结果写入 session 的一个"待确认记忆"队列
- summarize 节点（或生成最终回复的节点）检查队列
- 如果有待确认的记忆，在总结回复末尾加一句：
  ```
  另外，我记下了：amount 字段是商品原价，实付金额应该看 final_amount。
  以后我会注意这个区别 👌
  ```
- 确认完后从队列中移除，记忆标记为已确认（confidence 提升到 0.9）

**如果用户继续纠正（"不对，还是错了"）：**
- 新的纠错覆盖旧记忆（或者并存，旧的 confidence 降低）
- 再次确认新的理解

### 2.6 记忆注入 Schema Context

在 `_build_detailed_schema_context` 中，构建完原始 schema 后，追加用户记忆。

**注入位置**：
- 表级记忆 → 追加在表描述后面，用"📝 用户备注："标记
- 列级记忆 → 追加在对应列的行后面，用"  📝 用户备注: "标记
- 术语/指标记忆 → 放在 schema context 的最前面，作为"业务术语说明"区块

**示例效果：**

```
业务术语说明（来自用户备注）：
  · "流水" = GMV = 总交易额（2026-08-20）

=== 表: orders ===
描述: 记录用户下单信息
📝 用户备注: orders 表只存主站订单，不含小程序订单（2026-08-18，会话 #abc）
...

列:
  · total_amount: DECIMAL(10,2) 商品原价 → 范围: 0.01 ~ 99999.99
      📝 用户备注: 这是商品原价，实付金额看 final_amount（2026-08-20）
  · final_amount: DECIMAL(10,2) 实付金额 → 范围: 0.01 ~ 99999.99
```

### 2.7 记忆管理界面

在前端数据源设置中新增"Schema 记忆"标签页：

**功能**：
- 列表展示该数据源下的所有记忆（分页）
- 按类型筛选（列描述/表描述/指标定义/术语映射）
- 搜索（按实体名称、内容关键词）
- 编辑记忆内容
- 删除记忆
- 手动添加记忆
- 显示每条记忆的来源、时间、访问次数

**手动添加记忆的表单**：
- 记忆类型（下拉选择）
- 关联表（下拉选择当前数据源的表）
- 关联列（选了表之后可以选列，可选）
- 记忆内容（文本框）

### 2.8 与现有系统的集成点

| 文件/模块 | 改动 |
|-----------|------|
| `app/core/database.py` | 🆕 新增 `schema_memories` 表 |
| `app/services/memory_service.py` | 🆕 新增：记忆 CRUD + 召回服务 |
| `app/services/correction_detector.py` | 🆕 新增：纠错检测 + 记忆提取（LLM 调用） |
| `app/api/memories.py` | 🆕 新增：记忆管理 API |
| `nl2sql/agent/nodes/generate.py` | Schema context 注入用户记忆 |
| `app/services/chat_service.py` | 对话流程中加入异步纠错检测 |
| `nl2sql/agent/nodes/summarize.py` | 总结时加入隐式确认语句 |
| 前端 `components/settings/` | 🆕 新增：记忆管理页面 |
| 前端 `lib/api.ts` | 新增记忆相关 API 调用 |

---

## 三、实施计划

### 阶段划分

| 阶段 | 内容 | 预计工时 | 依赖 |
|------|------|---------|------|
| Phase 1 | Schema 信息增肥 | 5 个任务模块 | 无 |
| Phase 2 | 用户纠错记忆系统 | 7 个任务模块 | Phase 1 的 schema context 改造 |

### Phase 1: Schema 信息增肥

**任务 1.1：模型与数据层**
- [ ] 扩展 `Table` / `Column` 模型字段
- [ ] 改造 YAML loader 兼容新字段
- [ ] 编写单元测试

**任务 1.2：自动探测服务**
- [ ] 实现 `SchemaProfiler` 服务
- [ ] 表行数、样例数据、NULL 率统计
- [ ] 数值范围、类别型 Top 值统计
- [ ] 大表降级逻辑
- [ ] 探测结果写回 YAML
- [ ] 单元测试

**任务 1.3：Schema Context 输出改造**
- [ ] 改造 `_build_detailed_schema_context` 输出增肥格式
- [ ] 列信息紧凑格式化
- [ ] 样例数据表格格式化
- [ ] 列数多时的智能截断（高相关列在前）
- [ ] 同步改造 intent 节点的 schema context
- [ ] 测试验证：token 量控制、格式可读性

**任务 1.4：集成到服务层**
- [ ] Schema 导入后触发异步探测
- [ ] 新增探测状态 API（进度、结果）
- [ ] 前端数据源设置页增加"Schema 信息"展示
- [ ] 前端展示探测状态

**任务 1.5：联调与测试**
- [ ] 端到端测试：连接数据源 → 自动探测 → 查询验证
- [ ] 对比测试：增肥前后 SQL 生成准确率对比（用测试数据集）
- [ ] Bug 修复
- [ ] 文档更新

### Phase 2: 用户纠错记忆系统

**任务 2.1：数据模型与基础服务**
- [ ] 建表 `schema_memories`
- [ ] 实现 MemoryService（CRUD + 列表 + 召回）
- [ ] 单元测试

**任务 2.2：记忆管理 API + 前端页面**
- [ ] 记忆管理 API（列表/新增/编辑/删除）
- [ ] 前端记忆管理页面
- [ ] 手动添加记忆功能
- [ ] 联调测试

**任务 2.3：记忆注入 Schema Context**
- [ ] 改造 `_build_detailed_schema_context`，注入用户记忆
- [ ] 表级记忆、列级记忆、术语记忆的不同注入位置
- [ ] 格式化输出（带 📝 标记 + 时间）
- [ ] 测试验证

**任务 2.4：纠错检测服务**
- [ ] 实现纠错检测 LLM 调用（prompt 设计 + JSON 解析）
- [ ] 实现记忆提取逻辑（校验实体存在性等）
- [ ] 关键词预筛（减少不必要的 LLM 调用）
- [ ] 单元测试

**任务 2.5：集成到对话流程**
- [ ] chat_service 中加入异步纠错检测
- [ ] 待确认记忆队列机制
- [ ] summarize 节点中加入隐式确认
- [ ] 用户再次纠正时的记忆更新逻辑

**任务 2.6：前端交互 + 测试**
- [ ] 对话中确认语句的展示
- [ ] 端到端测试：用户纠正 → 检测 → 存储 → 下次生效
- [ ] 各种边界情况测试（不是纠错误判、提取错误、实体不存在等）

**任务 2.7：优化与联调**
- [ ] 误判率优化（调 prompt）
- [ ] 记忆召回准确性优化
- [ ] 性能优化（异步检测不影响主流程延迟）
- [ ] Bug 修复
- [ ] 文档更新

---

## 四、风险与注意事项

1. **探测对业务库的压力**：大表探测可能较慢或增加业务库负载。对策：异步执行、大表降级（采样/跳过）、低峰期执行。

2. **纠错误判**：系统可能把普通对话误判为纠错。对策：关键词预筛 + 严格的检测 prompt + 置信度机制 + 用户可在管理页删除。

3. **记忆质量**：自动提取的记忆可能不准确。对策：不覆盖原始 schema，只作为补充；置信度机制；用户可编辑删除。

4. **Token 成本增加**：Schema 增肥后 context 变大，每次 SQL 生成的 token 消耗增加。对策：列数多时做智能截断，只显示高相关列；表多时用两阶段检索（不在本期范围内）。

5. **向后兼容**：所有新增字段都有默认值，现有 YAML 文件和数据库不受影响。
