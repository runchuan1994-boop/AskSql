# NL2SQL Agent 设计文档

> 日期: 2026-08-19
> 状态: 待评审
> 版本: v1

## 一、项目概述

### 1.1 定位

面向内部数据分析场景的 NL2SQL（自然语言转 SQL）Agent 工具。用户用自然语言提问，Agent 自动理解意图、生成 SQL、在只读数据库中执行，并通过 ReAct 反思循环迭代优化，最终返回 SQL 和查询结果。

核心设计原则：**与业务充分解耦**——核心能力独立封装，业务数据通过配置注入。

### 1.2 目标用户

- 数据分析师
- 产品经理
- 需要查数据但不精通 SQL 的内部用户

### 1.3 核心流程

```
用户提问 → 意图分析 → SQL生成 → 沙盒执行 → ReAct反思 → 输出结果+SQL
                ↑                        │
                │  需要澄清？             │  不满意？
                └────────────────────────┘
```

## 二、整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        React 前端                           │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ 聊天界面  │  │ Schema 浏览  │  │ 结果展示(表格+SQL)    │  │
│  └────┬─────┘  └──────────────┘  └──────────────────────┘  │
└───────┼─────────────────────────────────────────────────────┘
        │ SSE (服务端推送) + REST (客户端发消息)
┌───────┼─────────────────────────────────────────────────────┐
│                    FastAPI 后端                              │
│  ┌──────────┐   ┌──────────────────────────────────────┐   │
│  │ 会话管理  │   │         LangGraph Agent              │   │
│  └────┬─────┘   │  ┌─────────┐    ┌────────────────┐   │   │
│       │         │  │ Intent  │───▶│ SQL Generator  │   │   │
│       │         │  │ Analyzer│    └───────┬────────┘   │   │
│       │         │  └─────────┘            │            │   │
│       │         │                   ┌─────▼──────┐     │   │
│       │         │    ┌──────────┐   │ SQL Executor│     │   │
│       │         │    │ ReAct    │◀──┤ (Sandbox)  │     │   │
│       │         │    │ Reflect  │   └────────────┘     │   │
│       │         │    └─────┬────┘                      │   │
│       │         │          │  (循环: 修改SQL/查Schema)  │   │
│       │         └──────────┼───────────────────────────┘   │
│       │                    │                               │
│  ┌────▼─────────┐  ┌───────▼─────────┐  ┌──────────────┐  │
│  │ Schema 服务  │  │ LLM 适配器      │  │ 数据库连接池  │  │
│  │ (自动导入)   │  │                 │  │              │  │
│  └──────────────┘  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | React + Vite + TypeScript + TailwindCSS + shadcn/ui | 现代前端技术栈 |
| 后端 | Python + FastAPI | 异步高性能 API 框架 |
| Agent 编排 | LangGraph | 状态机式的 Agent 流程编排，天然适合 ReAct 循环 |
| 通信 | SSE (Server-Sent Events) + REST | 流式推送 Agent 进展，REST 处理用户输入 |
| 数据库连接 | SQLAlchemy / 各数据库原生驱动 | 支持多类型数据库 |
| Schema 存储 | YAML 配置文件 | 与代码解耦，支持热加载 |
| 生成日志 | SQLite | 本地存储 SQL 生成记录，用于优化分析 |

### 2.3 目录结构

```
nl2sql/
├── frontend/                    # React 前端
│   ├── src/
│   │   ├── components/          # UI 组件
│   │   ├── hooks/               # 自定义 hooks (useSSE, useChat)
│   │   ├── pages/               # 页面
│   │   └── lib/                 # 工具函数
│   └── package.json
│
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── api/                 # 路由层
│   │   │   ├── chat.py          # 聊天相关接口
│   │   │   ├── stream.py        # SSE 流
│   │   │   ├── schema.py        # Schema 管理接口
│   │   │   ├── projects.py      # 项目管理接口
│   │   │   └── datasources.py   # 数据源管理接口
│   │   ├── services/            # 业务服务层
│   │   │   ├── session.py       # 会话管理
│   │   │   ├── generation_log.py # SQL 生成日志
│   │   │   ├── project.py       # 项目管理
│   │   │   └── schema_import.py # Schema 自动导入
│   │   └── core/                # 配置、依赖注入
│   │       ├── config.py
│   │       └── database.py
│   │
│   ├── nl2sql/                  # ★ 核心库（可独立 import）
│   │   ├── agent/               # LangGraph Agent
│   │   │   ├── graph.py         # 状态图定义
│   │   │   ├── state.py         # Graph State 定义
│   │   │   ├── nodes/           # 各个节点
│   │   │   │   ├── intent.py    # 意图分析
│   │   │   │   ├── probe.py     # 意图探查（用SQL消除歧义）
│   │   │   │   ├── clarify.py   # 澄清判断
│   │   │   │   ├── generate.py  # SQL 生成
│   │   │   │   ├── execute.py   # SQL 执行
│   │   │   │   └── reflect.py   # ReAct 反思
│   │   │   └── tools/           # ReAct 可用工具
│   │   │       ├── sql_executor.py
│   │   │       ├── schema_tools.py
│   │   │       └── ask_user.py
│   │   ├── schema/              # Schema 元数据管理
│   │   │   ├── models.py        # 数据模型
│   │   │   ├── loader.py        # 加载器（支持热加载）
│   │   │   ├── matcher.py       # 语义匹配
│   │   │   └── watcher.py       # 文件变化监听（热加载触发）
│   │   ├── llm/                 # LLM 适配器
│   │   │   ├── base.py          # 统一接口
│   │   │   ├── claude_client.py
│   │   │   ├── openai_client.py
│   │   │   └── factory.py       # 工厂函数
│   │   ├── executor/            # SQL 执行器
│   │   │   ├── base.py
│   │   │   ├── mysql_executor.py
│   │   │   ├── postgres_executor.py
│   │   │   └── factory.py
│   │   └── config.py
│   │
│   ├── config/                  # 运行时配置
│   │   ├── projects/            # 项目配置 (每个项目一个 yaml)
│   │   │   └── example.yaml
│   │   └── schemas/             # Schema 元数据
│   │       └── example/
│   │           ├── mysql.yaml
│   │           └── clickhouse.yaml
│   │
│   ├── data/                    # 本地数据
│   │   └── generation_log.db    # 生成日志 SQLite
│   │
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml
│
└── docs/
    └── superpowers/specs/
        └── 2026-08-19-nl2sql-agent-design.md  (本文档)
```

## 三、LangGraph Agent 设计（核心）

### 3.1 Graph State

```python
@dataclass
class AgentState:
    # 基本信息
    project_id: str
    datasource_ids: list[str]        # 可用数据源列表
    user_query: str                  # 当前用户问题
    conversation_history: list[Message]  # 对话历史

    # 意图分析结果
    intent: IntentResult | None = None
    probe_findings: list[ProbeFinding] = field(default_factory=list)  # 意图探查发现
    probe_iteration: int = 0
    max_probe_iterations: int = 3
    clarification_questions: list[str] = None  # 需要澄清的问题
    awaiting_clarification: bool = False

    # SQL 与执行
    sql: str | None = None
    execution_result: ExecutionResult | None = None

    # ReAct 循环
    react_thoughts: list[ReactThought] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5

    # 输出
    status: AgentStatus = AgentStatus.THINKING
    final_answer: str | None = None
    error: str | None = None
```

### 3.2 节点定义

| 节点 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `intent_analyze` | 分析用户意图，识别涉及的表/维度/筛选/聚合，标记歧义 | user_query, schema | intent, ambiguities |
| `intent_probe` | 主动探查：用轻量 SQL 查询消除歧义（查字段枚举值、采样数据、时间范围等） | intent.ambiguities, schema | probe_findings, 更新后的 intent |
| `need_clarify` | 条件判断：探查后仍有歧义需要向用户澄清 | intent.ambiguities, probe_findings | 分支: ask_clarify / generate_sql |
| `ask_clarify` | 生成澄清问题，暂停等待用户回复 | ambiguities | clarification_questions, status=clarifying |
| `generate_sql` | 根据意图生成 SQL | intent, schema, probe_findings | sql |
| `execute_sql` | 在沙盒中执行 SQL | sql | execution_result |
| `react_reflect` | ReAct 反思：判断结果是否回答了问题，决定下一步工具 | execution_result, react_thoughts | react_thought, next_action |
| `need_retry` | 条件判断：继续迭代还是输出 | reflection, iteration | 分支: generate_sql / summarize |
| `summarize` | 用自然语言总结结果 | execution_result, user_query | final_answer |

### 3.3 图结构

```
                    ┌──────────────────┐
                    │  intent_analyze  │  分析意图，标记歧义
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   intent_probe   │  主动探查：用轻量SQL消除歧义
                    │  (最多 3 次)      │  (字段枚举/采样/时间范围/表关联)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   need_clarify   │─── 是 ──▶  ask_clarify (暂停等待用户)
                    └────────┬─────────┘                  │
                             │ 否                          │ 用户回复后
                             ▼                              ▼
                    ┌──────────────────┐            回到 intent_analyze
                    │  generate_sql    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   execute_sql    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  react_reflect   │
                    └───┬──────────┬───┘
                        │ 修正      │ 满意
                        ▼          ▼
                 ┌───────────┐ ┌───────────┐
                 │ max_iter? │ │ summarize │
                 └───┬───┬───┘ └─────┬─────┘
                     │ 否  │是        │
                     ▼    ▼          ▼
              generate_sql  (终止)  END
```

### 3.4 ReAct 工具集

Agent 在反思阶段可以调用以下工具：

| 工具 | 用途 |
|------|------|
| `execute_sql(sql)` | 执行 SQL 查询（带超时和行数限制） |
| `list_tables(datasource_id?)` | 列出所有可用表 |
| `describe_table(table_name, datasource_id?)` | 查看表结构和字段说明 |
| `sample_data(table_name, n=10, datasource_id?)` | 查看表的前 N 行样本数据 |
| `ask_user(question)` | 向用户提问澄清（反思也搞不定时） |

### 3.5 意图探查（Intent Probe）

在正式生成 SQL 之前，Agent 可以用轻量 SQL 查询主动消除歧义，减少需要用户澄清的次数。

**可自动探查的歧义类型：**

| 歧义类型 | 探查方式 | 示例 |
|----------|----------|------|
| 字段含义不明 | 采样去重值 | "status 有哪些值？" → `SELECT DISTINCT status FROM t LIMIT 20` |
| 表名歧义 | 分别采样对比 | 用户说"订单"但有 `orders` 和 `order_items` → 各查 5 行对比语义 |
| 时间范围 | 查字段最大/最小值 | "最近的数据" → 查 `MAX(created_at)` 确认最新时间点 |
| 数据量级 | COUNT 估算 | "有多少用户" → 先看总量级，决定是否需要提示结果规模 |
| 表间关联 | 探查外键/共字段 | "用户订单" → 找两表之间的关联字段 |

**探查工具（轻量版，比 ReAct 工具更克制）：**

| 工具 | 用途 | 限制 |
|------|------|------|
| `probe_distinct(table, column, limit=20)` | 查字段去重值 | LIMIT 上限 50 |
| `probe_sample(table, limit=5)` | 采样表数据 | LIMIT 上限 20 |
| `probe_min_max(table, column)` | 查数值/时间字段范围 | 仅 1 行结果 |
| `probe_count(table)` | 查表总行数 | 仅 1 行结果 |
| `probe_relation(table1, table2)` | 探查两表关联字段 | 基于 schema 元数据 + 采样验证 |

**成本控制：**
- 最大探查迭代次数：3 次
- 单次探查 SQL 超时：5 秒
- 总探查时间上限：10 秒
- 探查过程通过 SSE 实时推送（事件类型: `intent_probe`）

**探查 vs 澄清的分工：**
- **探查搞定**：技术层面的歧义（数据实际长什么样、有哪些值、时间范围）
- **仍需澄清**：业务语义层面的歧义（"活跃用户"的定义、统计口径、业务规则）

### 3.6 澄清策略（混合式）

- **主动澄清（高优先级歧义）：**
  - 用户问题涉及的表不明确（多张表都可能匹配）
  - 关键维度缺失且没有合理默认值
  - 聚合方式不明确且影响结果结构

- **先猜后验证（低优先级歧义）：**
  - 时间范围默认（如"最近30天"）
  - 排序方式默认（如按时间倒序）
  - LIMIT 默认值
  - 这些在最终回答中说明"我默认按 XXX 处理的"

## 四、Schema 与多项目管理

### 4.1 项目与数据源模型

```
Project (项目)
  ├── id, name, description
  ├── Datasource[] (多个数据源)
  │    ├── id, name, type (mysql/postgres/clickhouse/...)
  │    ├── connection_info (加密存储)
  │    └── Schema (表 + 字段元数据)
  ├── Session[] (会话历史)
  └── GenerationLog[] (生成日志)
```

### 4.2 Schema 元数据格式（YAML）

```yaml
# config/schemas/project_id/datasource_id.yaml
datasource:
  id: mysql_main
  name: 主业务库
  type: mysql

tables:
  - name: users
    description: 用户表，记录所有注册用户的基本信息
    columns:
      - name: id
        type: bigint
        description: 用户ID，主键
        is_primary_key: true
      - name: email
        type: varchar(255)
        description: 注册邮箱
      - name: created_at
        type: datetime
        description: 注册时间
        semantic_type: timestamp
      - name: status
        type: varchar(20)
        description: 用户状态
        enum_values: [active, inactive, banned]
        semantic_type: category
      - name: country
        type: varchar(100)
        description: 注册国家
        semantic_type: dimension
    examples:
      - question: 上个月新增了多少用户
        sql: SELECT COUNT(*) FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
```

### 4.3 Schema 自动导入（V1 必备）

**流程：**

```
用户填写连接信息 (类型/地址/端口/账号/密码/库名)
        │
        ▼
   测试连接 ──失败──▶ 返回错误信息
        │ 成功
        ▼
   读取系统表 (information_schema / pg_catalog 等)
   - 表名、表注释
   - 字段名、字段类型、字段注释、是否主键
   - 索引信息、外键关系
        │
        ▼
   LLM 补充描述（可选，用户可开关）
   - 生成中文表/字段描述
   - 识别语义类型 (timestamp/amount/dimension/category)
   - 低基数字段采样枚举值
        │
        ▼
   前端预览，用户编辑确认
   - 修改描述
   - 删除不需要的表/字段
   - 补充业务含义
        │
        ▼
   保存为 YAML 文件 + 项目配置
```

**支持的导入模式：**
- **快速导入** — 只导入表结构和数据库原生注释
- **智能导入** — 快速导入 + LLM 生成描述 + 语义标签 + 枚举值采样

**安全要求：**
- 数据库密码加密存储（不写入 YAML 明文）
- 建议用户提供只读账号
- 导入操作有超时限制（默认 60s）

### 4.4 项目配置格式

```yaml
# config/projects/ecommerce.yaml
project:
  id: ecommerce
  name: 电商数据分析
  description: 电商业务全链路数据分析

datasources:
  - id: mysql_main
    name: 主业务库
    type: mysql
    connection_env: ECOMMERCE_MYSQL_URL
    schema_file: schemas/ecommerce/mysql_main.yaml

  - id: clickhouse_analytics
    name: 数仓
    type: clickhouse
    connection_env: ECOMMERCE_CK_URL
    schema_file: schemas/ecommerce/clickhouse_analytics.yaml
```

## 五、前端设计

### 5.1 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  项目: [电商数据分析 ▼]    新建会话    历史会话  ⚙设置   │
├──────────────────┬──────────────────────────────────────┤
│                  │                                      │
│  📊 Schema 面板  │           聊天对话区                  │
│                  │                                      │
│  ┌────────────┐ │  ┌────────────────────────────────┐  │
│  │ users      │ │  │ 用户: 上个月新增了多少用户？    │  │
│  │  ▾ 字段列表│ │  │                                │  │
│  │   • id     │ │  │ 🤖 正在分析意图...              │  │
│  │   • email  │ │  │                                │  │
│  │   • ...    │ │  │ 🤖 生成 SQL 中...               │  │
│  ├────────────┤ │  │                                │  │
│  │ orders     │ │  │ 🤖 执行查询中...                │  │
│  └────────────┘ │  │                                │  │
│                  │  │ 🤖 为您找到结果：              │  │
│  🔍 搜索表/字段  │  │                                │  │
│                  │  │  ┌── 结果表格 ──────────────┐  │  │
│                  │  │  │  count                  │  │  │
│  [导入数据源]   │  │  │  1,234                  │  │  │
│                  │  │  └─────────────────────────┘  │  │
│                  │  │                                │  │
│                  │  │  📝 生成的 SQL:                │  │
│                  │  │  ```sql                       │  │
│                  │  │  SELECT COUNT(*)              │  │
│                  │  │  FROM users                   │  │
│                  │  │  WHERE created_at >= ...      │  │
│                  │  │  ```                          │  │
│                  │  │  [📋复制] [💡解释] [🔄重新生成]│  │
│                  │  └────────────────────────────────┘  │
│                  │                                      │
│                  │  ┌──────────────────────────────┐    │
│                  │  │ 💬 输入你的问题...  [发送]   │    │
│                  │  └──────────────────────────────┘    │
└──────────────────┴──────────────────────────────────────┘
```

### 5.2 核心组件

| 组件 | 职责 |
|------|------|
| `ChatPanel` | 聊天主界面，消息流展示 |
| `ChatInput` | 输入框，支持发送问题 |
| `SchemaSidebar` | 左侧 Schema 浏览面板，支持搜索、展开表 |
| `ResultTable` | 查询结果表格，支持排序、复制、导出 CSV |
| `SqlDisplay` | SQL 代码展示，支持复制、解释、重新生成 |
| `ClarificationDialog` | 澄清问题弹窗/内联组件 |
| `ProjectSwitcher` | 项目切换下拉框 |
| `DatasourceManageModal` | 数据源管理（添加、导入、编辑） |
| `SessionList` | 会话历史列表 |

### 5.3 通信方式

**SSE 事件流：**

| 事件类型 | 触发时机 | 数据 |
|----------|----------|------|
| `intent_analysis` | 意图分析完成 | intent 摘要 |
| `intent_probe` | 意图探查（每次探查动作） | probe_action, finding |
| `sql_generated` | SQL 生成完成 | sql |
| `sql_executing` | 开始执行 SQL | - |
| `sql_executed` | SQL 执行完成 | execution_result |
| `reflection` | 反思推理 | thought, action |
| `clarification_needed` | 需要用户澄清 | questions |
| `final_result` | 最终结果 | answer, sql, result |
| `error` | 发生错误 | error_message |
| `done` | 流结束 | - |

**REST 接口：**

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects` | 获取项目列表 |
| POST | `/api/projects/{id}/datasources` | 添加数据源 |
| POST | `/api/datasources/test` | 测试数据库连接 |
| POST | `/api/datasources/{id}/import-schema` | 触发 Schema 导入 |
| GET | `/api/schema` | 获取当前项目 Schema |
| POST | `/api/chat` | 发送消息，返回 stream_id |
| POST | `/api/chat/{stream_id}/clarify` | 回复澄清问题 |
| GET | `/api/stream/{stream_id}` | SSE 流订阅 |
| GET | `/api/sessions` | 获取会话列表 |

## 六、LLM 适配器层

### 6.1 统一接口

```python
class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], tools: list[Tool] = None) -> ChatResponse:
        pass

    @abstractmethod
    def chat_stream(self, messages: list[Message], tools: list[Tool] = None) -> Iterator[ChatChunk]:
        pass
```

### 6.2 支持的提供商

| 提供商 | 实现方式 | 说明 |
|--------|----------|------|
| Claude | Anthropic SDK | 官方 SDK，支持 tool calling |
| OpenAI | OpenAI SDK | 官方 SDK |
| 本地模型 | OpenAI 兼容 SDK | Ollama / vLLM / LM Studio / OneAPI 等 |

### 6.3 配置方式 (.env)

```env
# ===== 模型配置 =====
LLM_PROVIDER=claude              # claude / openai / local_openai_compatible

# Claude 配置
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# OpenAI / 本地兼容配置
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=gpt-4o

# 嵌入模型（用于 schema 语义匹配，可选）
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

## 七、沙盒执行与安全

### 7.1 安全措施（V1: 方案 A）

| 措施 | 说明 | 默认值 |
|------|------|--------|
| **只读数据库账号** | 连接账号只有 SELECT 权限 | 强依赖用户配置 |
| **查询超时** | 单条 SQL 最大执行时间 | 30 秒 |
| **行数限制** | 自动追加 LIMIT 限制返回行数 | 1000 行 |
| **单语句限制** | 只允许单条 SQL，禁止多语句注入 | 启用 |
| **总时长限制** | 单次 Agent 运行最大时长 | 5 分钟 |

### 7.2 后续可升级

- SQL AST 解析白名单（sqlglot）
- 独立沙盒进程/容器
- 读写分离只读库（用户已规划）

## 八、生成日志

### 8.1 记录内容

每次 SQL 生成迭代都记录：

```json
{
  "id": "uuid",
  "timestamp": "2026-08-19T10:00:00Z",
  "project_id": "ecommerce",
  "datasource_id": "mysql_main",
  "session_id": "xxx",
  "user_query": "上个月新增用户数",
  "conversation_history": [...],
  "generated_sql": "SELECT COUNT(*) FROM users WHERE ...",
  "intent_summary": "聚合: COUNT, 表: users, 筛选: 上个月",
  "execution_success": true,
  "execution_time_ms": 120,
  "row_count": 1,
  "error_message": null,
  "iteration": 2,
  "reflection_notes": "第一次漏了 status 过滤，已修正",
  "user_feedback": null,
  "model": "claude-sonnet-4-20250514",
  "final_selected": true
}
```

### 8.2 存储方式

- V1: 本地 SQLite 数据库
- 后续可扩展: 接入远程数据库、支持查询分析 dashboard

### 8.3 用途

- Prompt 优化：分析失败案例，改进 prompt
- 模型对比：不同模型的准确率对比
- 用户行为分析：常见问题类型统计
- 后续 RLHF：用户点赞/点踩反馈

## 九、多轮对话与会话管理

### 9.1 会话模型

```
Session
  ├── id, project_id
  ├── title (自动生成)
  ├── messages: Message[]
  │    ├── role: user/assistant
  │    ├── content: 文本
  │    ├── sql?: 生成的 SQL
  │    ├── result?: 执行结果
  │    └── timestamp
  ├── created_at
  └── updated_at
```

### 9.2 多轮处理

- 每个会话内保留完整对话历史
- 历史上下文随每次请求传入 Agent
- 当对话过长时，自动摘要压缩旧消息（保留最近 N 轮完整 + 更早的摘要）
- 切换会话清空当前 Agent 状态

## 十、错误处理

### 10.1 错误分类与处理

| 错误类型 | 处理方式 | 用户感知 |
|----------|----------|----------|
| SQL 语法错误 | 捕获错误，送回 ReAct 循环让 Agent 修正 | 看到反思过程，最终修正后的结果 |
| 表/字段不存在 | 同上 | 同上 |
| 执行超时 | 终止执行，返回超时提示 | 看到超时错误 + 当前 SQL |
| 数据库连接失败 | 立即终止，返回连接错误 | 看到错误信息 + 排查建议 |
| LLM 调用超时/限流 | 指数退避重试（最多3次） | 体验变慢，但通常会成功 |
| LLM API 错误 | 重试失败后返回友好错误 | 看到错误，可以重试 |
| ReAct 达到最大迭代 | 终止循环，返回最后结果 | 看到结果 + "达到最大迭代次数"提示 |
| Schema 加载失败 | 返回错误，提示检查配置 | 看到错误信息 |

## 十一、V1 范围与非目标

### 11.1 V1 包含

- ✅ LangGraph ReAct Agent 核心流程
- ✅ 多轮对话与会话管理
- ✅ 多项目 / 多数据源支持
- ✅ Schema 自动导入（从数据库连接）
- ✅ YAML Schema 元数据管理
- ✅ LLM 多提供商适配（Claude / OpenAI / 本地兼容）
- ✅ SSE 流式输出
- ✅ React 前端（聊天 + Schema 面板 + 结果展示）
- ✅ 沙盒执行安全（只读账号 + 超时 + 行数限制）
- ✅ SQL 生成日志

### 11.2 V1 不包含（后续迭代）

- ❌ 跨库 JOIN 查询（V1 只支持单数据源内查询）
- ❌ SQL AST 白名单解析
- ❌ 用户系统 / 权限控制
- ❌ 可视化图表（V1 只输出表格）
- ❌ 查询结果缓存
- ❌ 团队协作 / 分享
- ❌ 自然语言到图表（Text-to-Chart）
