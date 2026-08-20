# nl2sql 核心库

自然语言转 SQL 的 Agent 库，基于 LangGraph 实现 ReAct 反思循环。

## 功能特性

- 🧠 **意图分析** — 自动识别查询涉及的表、维度、筛选条件、聚合方式
- 🔍 **意图探查** — 用轻量 SQL 自动消除歧义（字段枚举、数据采样、时间范围等）
- ❓ **混合式澄清** — 关键歧义主动问用户，次要歧义先猜后验证
- 📝 **SQL 生成** — 根据 Schema 和意图生成准确的 SQL
- 🛡️ **沙盒执行** — 只读安全保护，超时 + 行数限制 + 单语句限制
- 🔄 **ReAct 反思** — 自动检查结果，迭代优化 SQL（最多 N 次）
- 💬 **多轮对话** — 支持会话内上下文追问
- 🗄️ **多数据源** — 支持 MySQL / PostgreSQL / SQLite / ClickHouse 等 SQLAlchemy 兼容数据库
- 🤖 **多 LLM 支持** — Claude / OpenAI / 本地 OpenAI 兼容模型

## 架构

```
用户提问
  → intent_analyze  (意图分析: 识别表/维度/筛选/聚合)
  → intent_probe    (主动探查: 用轻量SQL消除歧义)
  → clarify         (判断是否需要用户澄清)
  → generate_sql    (生成 SQL)
  → execute_sql     (沙盒执行)
  → reflect         (反思校验)
  → 循环修正 / 输出总结
```

## 快速开始

### 安装

```bash
cd backend
uv pip install -e ".[dev]"
# 或者
pip install -e ".[dev]"
```

### 配置

复制环境变量示例文件：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API 配置：

```env
LLM_PROVIDER=claude              # claude / openai / local_openai_compatible
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

### 基本用法

```python
from nl2sql import NL2SQLAgent
from nl2sql.schema import SchemaLoader
from nl2sql.executor import create_executor

# 1. 加载 Schema
loader = SchemaLoader()
datasource = loader.load_from_yaml("config/schemas/sample/ecommerce.yaml")

# 2. 创建 SQL 执行器
executor = create_executor(
    datasource_id=datasource.datasource_id,
    datasource_type=datasource.datasource_type,
    db_url="mysql://user:pass@localhost:3306/dbname",
    timeout_seconds=30,
    max_rows=1000,
)

# 3. 创建 Agent
agent = NL2SQLAgent(
    project_id="ecommerce",
    datasources=[datasource],
    executors={datasource.datasource_id: executor},
    max_iterations=5,
    max_probe_iterations=3,
)

# 4. 运行查询
result = agent.run("上个月新增了多少用户？")

print(f"回答: {result['answer']}")
print(f"SQL: {result['sql']}")
print(f"迭代次数: {result['iteration']}")
print(f"状态: {result['status']}")
```

### 流式使用

```python
for event in agent.stream("上个月新增了多少用户？"):
    for node_name, node_state in event.items():
        print(f"[{node_name}] status={node_state.status}")
```

## 项目结构

```
nl2sql/
├── __init__.py          # 公共 API
├── config.py            # 全局配置
├── schema/              # Schema 元数据管理
│   ├── models.py        # Column / Table / Schema / DatasourceSchema
│   ├── loader.py        # YAML 加载器
│   ├── matcher.py       # 语义匹配器
│   └── watcher.py       # 热加载（预留）
├── llm/                 # LLM 适配层
│   ├── message.py       # Message / ToolCall 等数据模型
│   ├── base.py          # LLMClient 抽象基类
│   ├── claude_client.py # Claude 实现
│   ├── openai_client.py # OpenAI / 本地兼容实现
│   └── factory.py       # 工厂函数
├── executor/            # SQL 执行器
│   ├── models.py        # ExecutionResult
│   ├── base.py          # SQLExecutor 抽象基类
│   ├── generic_executor.py  # SQLAlchemy 通用执行器
│   └── factory.py       # 工厂函数
└── agent/               # Agent 核心
    ├── state.py         # AgentState / IntentResult 等状态模型
    ├── graph.py         # LangGraph 图构建 + NL2SQLAgent 入口
    ├── nodes/           # 图节点实现
    │   ├── intent.py    # 意图分析
    │   ├── probe.py     # 意图探查
    │   ├── clarify.py   # 澄清判断
    │   ├── generate.py  # SQL 生成
    │   ├── execute.py   # SQL 执行
    │   ├── reflect.py   # ReAct 反思
    │   └── summarize.py # 结果总结
    └── tools/           # Agent 工具集
        ├── schema_tools.py   # list_tables / describe_table
        ├── sql_tool.py       # execute_sql
        └── probe_tools.py    # 探查工具（4个）
```

## Schema 配置格式

```yaml
datasource:
  id: ecommerce_mysql
  name: 电商 MySQL 库
  type: mysql

tables:
  - name: users
    description: 用户表，记录所有注册用户
    columns:
      - name: id
        type: bigint
        description: 用户ID，主键
        is_primary_key: true
        semantic_type: id
      - name: status
        type: varchar(20)
        description: 用户状态
        enum_values: [active, inactive, banned]
        semantic_type: category
      - name: created_at
        type: datetime
        description: 注册时间
        semantic_type: timestamp
    examples:
      - question: 上个月新增了多少用户
        sql: SELECT COUNT(*) FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
```

## 运行测试

```bash
cd backend
uv run pytest tests/ -v
```

当前测试覆盖率：**139 个测试全部通过**。

## 安全说明

V1 版本的安全措施：
- 只读数据库账号（强烈建议）
- SQL 语句校验：只允许 SELECT / SHOW / DESCRIBE / EXPLAIN / WITH
- 单语句限制：禁止多语句 SQL 注入
- 查询超时：默认 30 秒
- 行数限制：默认 1000 行

后续可升级：
- SQL AST 白名单解析（sqlglot）
- 独立沙盒进程

## License

MIT
