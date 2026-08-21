# Agentic Datasource Management（智能数据源管理）设计文档

> **功能：** 用户在对话框中用自然语言描述数据库连接信息，Agent 自动完成数据源创建、连接测试、Schema 导入，全程无需手动填写表单。

---

## 1. 背景与目标

### 1.1 现状

当前数据源管理通过 API + 前端表单完成，用户需要手动填写数据库类型、地址、端口、账号、密码等字段，操作繁琐。

### 1.2 目标

用户在对话中用自然语言描述即可完成数据源接入：

```
用户: "帮我连接一个 MySQL 数据库，地址 192.168.1.100，端口 3306，
       数据库名 ecommerce，账号 admin，密码 123456"

AI: "好的，正在创建数据源... 连接测试成功！检测到 12 张表，
     正在导入 Schema... 已完成。你可以开始查询了，比如'上个月销售额是多少？'"
```

### 1.3 核心特性

- 自然语言解析连接参数（数据库类型、地址、端口、库名、账号、密码）
- 自动创建数据源（Fernet 加密存储密码）
- 自动测试连接，失败时提示用户修正
- 自动导入 Schema
- 数据源归属当前会话所在的项目

---

## 2. 架构设计

### 2.1 Agent 图变更

在现有图中增加数据源连接分支：

```
intent_analyze → intent_probe → clarify
                                   ↓
                    ┌──────────┴──────────┐
                    │ 意图分类判断       │
                    ▼                     ▼
             connect_datasource       generate_sql
                    │                     │
             import_schema            execute_sql
                    │                     │
             summarize_ds               reflect
                    │                     │
                    └────── END ◄────────┘
```

### 2.2 意图分类

在 `intent_analyze` 节点的输出中增加 `action` 字段：

```python
class IntentResult(BaseModel):
    # ... 现有字段 ...
    action: str = "query"  # query / connect_datasource / manage_schema / ...
```

- `query`：正常查数据（现有流程）
- `connect_datasource`：连接新数据源（走新分支）

### 2.3 新增节点

| 节点 | 职责 |
|------|------|
| `connect_datasource_node` | 解析连接信息 → 创建数据源 → 测试连接 → 导入 Schema → 总结 |

### 2.4 新增工具

Agent 通过工具调用完成实际操作：

| 工具 | 功能 | 参数 |
|------|------|------|
| `create_datasource` | 创建数据源 | name, type, host, port, database, username, password |
| `test_connection` | 测试连接 | datasource_id |
| `import_schema` | 导入 Schema | datasource_id, use_llm |

工具层直接调用现有的 `datasource_service` 和 `schema_import` 服务。

---

## 3. 节点详细设计

### 3.1 intent_analyze 节点扩展

系统提示词中增加意图分类说明：

```
你的任务是分析用户查询的意图。

首先判断用户意图类型（action）：
- query: 用户想查询数据、分析数据、看报表（默认）
- connect_datasource: 用户想连接/添加/配置一个新的数据库或数据源

如果是 connect_datasource，还需要：
- 尽可能提取连接信息（数据库类型、地址、端口、库名、账号、密码）
- 识别用户是否是想"测试连接"或"重新连接"已有数据源
```

输出的 IntentResult 中增加：
```python
    action: str = "query"  # query / connect_datasource
    datasource_info: dict = Field(default_factory=dict)  # 提取到的连接信息
```

### 3.2 connect_datasource_node

这是一个轻量级的 ReAct 节点（最多 3 次迭代），职责：

1. 从用户查询和 intent 中提取连接参数
2. 调用 `create_datasource` 工具创建数据源
3. 调用 `test_connection` 工具测试连接
4. 如果连接失败，分析错误原因，询问用户修正（澄清流程）
5. 连接成功后，调用 `import_schema` 工具导入 Schema
6. 生成总结回复

**输入**：`user_query`, `intent`, `project_id`
**输出**：`final_answer`, `status`, `datasource_id`, `tables_imported`

### 3.3 澄清节点复用

现有 clarify 节点和 ask_clarify 节点可以复用——如果连接信息缺失（比如用户没说密码），走澄清流程问用户。

---

## 4. 工具设计

### 4.1 数据源工具集

在 `nl2sql/agent/tools/` 下新增 `datasource_tools.py`：

```python
"""数据源管理工具集.

供 Agent 调用，实现数据源的创建、连接测试、Schema 导入等操作.
"""
from __future__ import annotations

from typing import Any
from nl2sql.agent.tools.schema_tools import _validate_datasource_id  # 如需要


def get_datasource_tools(project_id: str) -> list[dict]:
    """获取数据源管理工具列表."""
    return [
        {
            "name": "create_datasource",
            "description": "创建一个新的数据源连接。用于用户想添加/连接/配置新数据库时。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "数据源名称，简短描述即可，如'电商 MySQL'。"},
                    "type": {"type": "string", "enum": ["mysql", "postgres", "sqlite", "clickhouse"], "description": "数据库类型。"},
                    "host": {"type": "string", "description": "数据库地址/主机名。sqlite 不需要。"},
                    "port": {"type": "integer", "description": "端口号。mysql 默认 3306，postgres 默认 5432。"},
                    "database": {"type": "string", "description": "数据库名。sqlite 时为文件路径。"},
                    "username": {"type": "string", "description": "用户名。"},
                    "password": {"type": "string", "description": "密码。"},
                },
                "required": ["name", "type", "database"],
            },
        },
        {
            "name": "test_connection",
            "description": "测试指定数据源是否能正常连接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {"type": "string", "description": "数据源 ID。"},
                },
                "required": ["datasource_id"],
            },
        },
        {
            "name": "import_schema",
            "description": "从数据库中导入表结构和 Schema 元数据。导入后才能用于查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {"type": "string", "description": "数据源 ID。"},
                },
                "required": ["datasource_id"],
            },
        },
    ]


def execute_datasource_tool(name: str, args: dict[str, Any], project_id: str) -> dict[str, Any]:
    """执行数据源工具.
    
    Args:
        name: 工具名称
        args: 工具参数
        project_id: 项目 ID
    
    Returns:
        工具执行结果 dict
    """
    # 延迟导入，避免循环依赖
    from app.services import datasource_service, schema_import

    if name == "create_datasource":
        ds = datasource_service.create_datasource(
            project_id=project_id,
            name=args.get("name", "未命名数据源"),
            ds_type=args.get("type", "mysql"),
            host=args.get("host", ""),
            port=args.get("port"),
            database=args.get("database", ""),
            username=args.get("username", ""),
            password=args.get("password", ""),
        )
        # 不返回密码
        return {
            "success": True,
            "datasource_id": ds["id"],
            "name": ds["name"],
            "type": ds["type"],
        }

    elif name == "test_connection":
        ds_id = args.get("datasource_id", "")
        success, message = datasource_service.test_connection_by_id(ds_id)
        return {
            "success": success,
            "message": message,
        }

    elif name == "import_schema":
        ds_id = args.get("datasource_id", "")
        result = schema_import.import_schema_from_database(ds_id)
        return result

    else:
        return {"error": f"Unknown tool: {name}"}
```

---

## 5. 图集成方案

### 5.1 条件边

新增条件函数 `need_connect_datasource`：

```python
def need_connect_datasource(state: dict) -> str:
    """判断是否需要走数据源连接分支."""
    intent = state.get("intent")
    if intent and getattr(intent, "action", None) == "connect_datasource":
        return "connect_datasource"
    return "generate_sql"
```

修改图结构：
- `clarify` 节点的条件边从 `ask_clarify / generate_sql` 改为 `ask_clarify / connect_datasource / generate_sql`
- 或者：clarify 之后新增一个路由节点/条件边

**最简洁的方案：** 在 clarify 之后直接根据 intent.action 路由。

```python
# clarify → 条件路由 → connect_datasource / generate_sql
graph.add_conditional_edges(
    "clarify",
    route_after_clarify,
    {
        "ask_clarify": "ask_clarify",
        "connect_datasource": "connect_datasource",
        "generate_sql": "generate_sql",
    },
)

# connect_datasource → END（或者经过一个简单的总结节点）
graph.add_edge("connect_datasource", "summarize_ds")
graph.add_edge("summarize_ds", END)
```

### 5.2 简化：一个节点搞定

`connect_datasource_node` 本身包含了创建、测试、导入、总结的全过程，所以它直接输出最终答案，不需要再经过 reflect/summarize 节点。

图结构：
```
clarify → [条件] → connect_datasource → END
                ↘ generate_sql → execute → reflect → summarize → END
```

---

## 6. 状态模型变更

`AgentState` 增加字段：

```python
    # 数据源连接
    datasource_id: Optional[str] = None
    tables_imported: int = 0
```

`IntentResult` 增加字段：

```python
    action: str = "query"  # query / connect_datasource
    datasource_info: dict = Field(default_factory=dict)
```

---

## 7. SSE 事件

新增事件：

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `ds_creating` | 开始创建数据源 | `{ name, type }` |
| `ds_created` | 数据源创建完成 | `{ datasource_id, name, type }` |
| `ds_testing` | 正在测试连接 | `{ datasource_id }` |
| `ds_connected` | 连接测试成功 | `{ datasource_id }` |
| `ds_connection_failed` | 连接失败 | `{ datasource_id, error }` |
| `ds_importing` | 正在导入 Schema | `{ datasource_id }` |
| `ds_imported` | Schema 导入完成 | `{ datasource_id, table_count, tables: [...] }` |

前端 `ThinkingStages` 增加：
- `connecting_datasource` → "连接数据源"
- `importing_schema` → "导入 Schema"

---

## 8. 前端变更

### 8.1 类型定义

- `SseEventType` 增加上面列出的 7 个 ds_* 事件
- `ThinkingStage` 增加 `connecting_datasource`, `importing_schema`
- `THINKING_STAGES` 数组增加对应阶段

### 8.2 useChat hook

- 处理新增的 SSE 事件，更新 currentStage
- 连接完成后，刷新 Schema 列表（可选，V2 再做）

### 8.3 其他

- Schema 面板连接完成后刷新（可选，V1 可以让用户手动刷新或下次进入时加载）

---

## 9. 错误处理

| 场景 | 处理方式 |
|------|---------|
| 缺少必要参数（无密码等） | 走澄清流程，问用户要 |
| 连接失败 | AI 分析错误信息，告诉用户原因，请用户修正参数后重试 |
| Schema 导入失败 | 告诉用户失败原因，数据源仍可使用（但无法查数据） |
| 数据库类型无法识别 | 询问用户确认类型 |

---

## 10. 安全考虑

1. 密码仍然通过 Fernet 加密存储（复用现有机制）
2. Agent 的工具调用日志中不记录密码明文
3. 前端 SSE 事件数据中不含密码
4. 聊天消息中不保存密码（只在数据源表中加密存储）

---

## 11. 实施顺序

1. **intent 节点扩展** — 增加 action 分类 + datasource_info 提取
2. **数据源工具集** — 新增 datasource_tools.py
3. **connect_datasource 节点** — 核心节点实现
4. **Agent 图改造** — 接入新分支和条件路由
5. **SSE 事件** — 新增事件推送
6. **前端适配** — 类型、思考阶段、事件处理
7. **测试** — 单元测试 + 集成测试
