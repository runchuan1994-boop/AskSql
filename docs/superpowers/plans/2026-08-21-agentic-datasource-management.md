# Agentic Datasource Management 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在对话中用自然语言描述即可完成数据源接入——Agent 自动解析连接信息、创建数据源、测试连接、导入 Schema。

**Architecture:** 在 Agent 图中增加 connect_datasource 分支。intent 节点识别出"连接数据源"意图后，走独立的连接流程：创建数据源 → 测试连接 → 导入 Schema → 总结回复。新增 datasource_tools 工具集封装后端服务调用。

**Tech Stack:** Python / LangGraph / FastAPI (后端), React + TypeScript (前端)

---

## 任务分解

| Task | 范围 | 产出 |
|------|------|------|
| Task 1 | 后端: intent 节点扩展 + 工具集 | action 分类、datasource_tools.py |
| Task 2 | 后端: connect_datasource 节点 | 核心节点实现 |
| Task 3 | 后端: Agent 图接入 + 条件路由 | 图改造、事件推送 |
| Task 4 | 前端: 类型 + 思考阶段 + 事件处理 | 前端适配 |
| Task 5 | 测试 + 验证 | 全量测试通过 |

---

## Task 1: intent 节点扩展 + 数据源工具集

**Files:**
- Modify: `backend/nl2sql/agent/nodes/intent.py` — 增加 action 分类和 datasource_info 提取
- Modify: `backend/nl2sql/agent/state.py` — IntentResult 增加 action + datasource_info
- Create: `backend/nl2sql/agent/tools/datasource_tools.py` — 数据源管理工具集
- Modify: `backend/nl2sql/agent/tools/__init__.py` — 导出
- Test: `backend/tests/test_agent/test_tools.py` — 增加数据源工具测试

### Step 1: 扩展 IntentResult 模型

在 `nl2sql/agent/state.py` 的 `IntentResult` 类中增加：

```python
    action: str = "query"  # query / connect_datasource
    datasource_info: dict = Field(default_factory=dict)  # 提取到的连接信息
```

### Step 2: 扩展 intent 分析系统提示词

在 `nl2sql/agent/nodes/intent.py` 的系统提示词中，增加意图分类说明。

在 INTENT_SYSTEM_PROMPT 中，输出格式说明部分增加：

```
首先判断用户意图的 action 类型：
- query: 用户想查询数据、分析数据、看报表（默认）
- connect_datasource: 用户想连接/添加/配置一个新的数据库或数据源

如果是 connect_datasource，datasource_info 中尽可能提取：
- type: 数据库类型 (mysql/postgres/sqlite/clickhouse)
- host: 地址
- port: 端口
- database: 数据库名
- username: 用户名
- password: 密码
- name: 数据源名称（可选）
```

在输出的 JSON 结构定义中增加 `action` 和 `datasource_info` 字段。

### Step 3: 修改 intent_analyze_node 的输出解析

确保解析 JSON 时正确处理新增的 action 和 datasource_info 字段。如果 LLM 没返回 action，默认为 "query"。

### Step 4: 创建数据源工具集

创建 `nl2sql/agent/tools/datasource_tools.py`：

```python
"""数据源管理工具集.

供 Agent 调用，实现数据源的创建、连接测试、Schema 导入等操作.
"""
from __future__ import annotations

from typing import Any


# 工具定义
DATASOURCE_TOOLS = [
    {
        "name": "create_datasource",
        "description": (
            "创建一个新的数据源连接。当用户想添加、连接、配置新的数据库或数据源时使用。"
            "创建成功后返回数据源 ID，后续可以用 test_connection 和 import_schema 工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "数据源名称，简短描述，如'电商 MySQL'。如果用户没指定，可以用数据库名+类型组合。",
                },
                "type": {
                    "type": "string",
                    "enum": ["mysql", "postgres", "sqlite", "clickhouse"],
                    "description": "数据库类型。根据用户描述判断，常见的有 mysql、postgres、sqlite。",
                },
                "host": {
                    "type": "string",
                    "description": "数据库主机地址/IP。sqlite 类型不需要。",
                },
                "port": {
                    "type": "integer",
                    "description": "端口号。MySQL 默认 3306，PostgreSQL 默认 5432，ClickHouse 默认 8123。",
                },
                "database": {
                    "type": "string",
                    "description": "数据库名。sqlite 时为文件路径。",
                },
                "username": {
                    "type": "string",
                    "description": "数据库用户名。",
                },
                "password": {
                    "type": "string",
                    "description": "数据库密码。",
                },
            },
            "required": ["name", "type", "database"],
        },
    },
    {
        "name": "test_connection",
        "description": "测试指定的数据源是否能正常连接。创建数据源后应该先测试连接。",
        "parameters": {
            "type": "object",
            "properties": {
                "datasource_id": {
                    "type": "string",
                    "description": "要测试的数据源 ID（从 create_datasource 返回）。",
                },
            },
            "required": ["datasource_id"],
        },
    },
    {
        "name": "import_schema",
        "description": (
            "从数据库中导入表结构和 Schema 元数据。"
            "导入成功后，这个数据源才能用于 SQL 查询。"
            "连接测试成功后再调用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "datasource_id": {
                    "type": "string",
                    "description": "数据源 ID。",
                },
            },
            "required": ["datasource_id"],
        },
    },
]


def execute_datasource_tool(
    name: str,
    args: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    """执行数据源管理工具.

    Args:
        name: 工具名称
        args: 工具参数字典
        project_id: 项目 ID（数据源归属的项目）

    Returns:
        工具执行结果字典
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

### Step 5: 更新 tools/__init__.py

在 `nl2sql/agent/tools/__init__.py` 中导出数据源工具：

```python
from .datasource_tools import DATASOURCE_TOOLS, execute_datasource_tool
```

### Step 6: 增加工具测试

在 `tests/test_agent/test_tools.py` 中增加数据源工具的测试（用 mock，不实际连数据库）。测试点：
- DATASOURCE_TOOLS 定义正确
- create_datasource 工具调用成功
- test_connection 工具返回正确结构
- import_schema 工具返回正确结构
- 未知工具返回 error

### Step 7: 运行测试

```bash
cd backend
.venv/bin/python -m pytest tests/test_agent/test_tools.py -v --tb=short
```
Expected: 全部通过

### Step 8: 全量测试

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```
Expected: 全部通过（249 + 新增）

### Step 9: Commit

```bash
git add nl2sql/agent/nodes/intent.py nl2sql/agent/state.py nl2sql/agent/tools/datasource_tools.py nl2sql/agent/tools/__init__.py tests/test_agent/test_tools.py
git commit -m "feat(agent): extend intent with action classification + datasource tools"
```

---

## Task 2: connect_datasource 节点

**Files:**
- Create: `backend/nl2sql/agent/nodes/connect_datasource.py`
- Modify: `backend/nl2sql/agent/nodes/__init__.py` — 导出
- Test: `backend/tests/test_agent/test_nodes_connect_ds.py`

### Step 1: 创建 connect_datasource 节点

创建 `nl2sql/agent/nodes/connect_datasource.py`。

这个节点负责：
1. 接收用户查询和 intent（内含 datasource_info）
2. 向 LLM 发送指令，让其决定调用哪些工具
3. 执行工具调用（create_datasource → test_connection → import_schema）
4. 生成最终回复

实现方式：**直接用 LLM + 工具调用**，写一个简单的单轮 tool_use 循环（最多 3 次工具调用）。

不需要用 LangGraph，因为这是图里的一个节点，节点内部直接用 LLM 的 tool_calls 能力做 2-3 轮交互即可。

```python
"""Connect datasource node: Agent 自动创建数据源、测试连接、导入 Schema.

这是 Agent 图中的一个节点。当用户意图是连接数据源时，走这个节点。
节点内部使用 LLM 的 tool_calls 能力，最多 3 轮工具调用，完成整个连接流程。
"""
from __future__ import annotations

from typing import TYPE_CHECKING
import json

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client
from nl2sql.agent.tools.datasource_tools import (
    DATASOURCE_TOOLS,
    execute_datasource_tool,
)

if TYPE_CHECKING:
    from ..state import AgentState


CONNECT_DS_SYSTEM_PROMPT = """你是一位数据库连接专家。你的任务是帮助用户创建和配置数据源连接。

工作流程：
1. 分析用户提供的连接信息
2. 如果信息充足，调用 create_datasource 工具创建数据源
3. 创建后立即调用 test_connection 测试连接
4. 连接成功后调用 import_schema 导入表结构
5. 用自然语言总结结果告诉用户

注意事项：
- 如果缺少必要信息（如密码），不要瞎猜，直接告诉用户需要什么信息
- 连接失败时，把错误信息告诉用户，让用户检查参数
- 密码等敏感信息不要在回复中重复
- 回复简洁友好，用中文
- 完成导入后，告诉用户有多少张表，并举 1-2 个可以问的问题示例
"""


def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def connect_datasource_node(state: dict) -> dict:
    """连接数据源节点.

    Returns:
        dict with final_answer, status, datasource_id, tables_imported
    """
    user_query = state.get("user_query", "")
    project_id = state.get("project_id", "")
    intent = state.get("intent")

    # 从 intent 中预提取的信息
    ds_info = {}
    if intent and hasattr(intent, "datasource_info"):
        ds_info = intent.datasource_info or {}

    # 构建初始用户消息
    initial_msg = f"用户想连接一个数据源。\n用户说：{user_query}\n\n"
    if ds_info:
        initial_msg += f"已提取的信息：\n{json.dumps(ds_info, ensure_ascii=False, indent=2)}\n\n"
    initial_msg += "请帮用户完成数据源的创建、连接测试和 Schema 导入。"

    messages = [
        Message(role=MessageRole.SYSTEM, content=CONNECT_DS_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=initial_msg),
    ]

    llm = create_llm_client()
    tools = DATASOURCE_TOOLS

    datasource_id = None
    tables_imported = 0
    max_iterations = 4

    for i in range(max_iterations):
        response = llm.chat(messages, tools=tools, temperature=0.0)

        if not response.tool_calls:
            # LLM 返回了最终文字回复
            final_answer = response.content.strip()
            _send_event(state, "final_result", {
                "answer": final_answer,
                "success": True,
                "datasource_id": datasource_id,
                "tables_imported": tables_imported,
            })
            return {
                "final_answer": final_answer,
                "status": "done",
                "datasource_id": datasource_id,
                "tables_imported": tables_imported,
            }

        # 处理工具调用
        tool_messages = []
        for tc in response.tool_calls:
            tool_name = tc.name
            try:
                tool_args = tc.arguments if isinstance(tc.arguments, dict) else json.loads(tc.arguments)
            except (json.JSONDecodeError, TypeError):
                tool_args = {}

            # 发送进度事件
            if tool_name == "create_datasource":
                _send_event(state, "ds_creating", {
                    "name": tool_args.get("name", ""),
                    "type": tool_args.get("type", ""),
                })
            elif tool_name == "test_connection":
                _send_event(state, "ds_testing", {
                    "datasource_id": tool_args.get("datasource_id", ""),
                })
            elif tool_name == "import_schema":
                _send_event(state, "ds_importing", {
                    "datasource_id": tool_args.get("datasource_id", ""),
                })

            # 执行工具
            result = execute_datasource_tool(tool_name, tool_args, project_id)

            # 记录关键信息
            if tool_name == "create_datasource" and result.get("success"):
                datasource_id = result.get("datasource_id")
                _send_event(state, "ds_created", {
                    "datasource_id": datasource_id,
                    "name": result.get("name", ""),
                    "type": result.get("type", ""),
                })
            elif tool_name == "test_connection":
                if result.get("success"):
                    _send_event(state, "ds_connected", {
                        "datasource_id": tool_args.get("datasource_id", ""),
                    })
                else:
                    _send_event(state, "ds_connection_failed", {
                        "datasource_id": tool_args.get("datasource_id", ""),
                        "error": result.get("message", ""),
                    })
            elif tool_name == "import_schema":
                if result.get("success"):
                    tables_imported = result.get("table_count", 0)
                    _send_event(state, "ds_imported", {
                        "datasource_id": tool_args.get("datasource_id", ""),
                        "table_count": tables_imported,
                    })

            tool_messages.append(Message(
                role=MessageRole.TOOL,
                content=json.dumps(result, ensure_ascii=False),
                tool_result=type('obj', (), {
                    'tool_call_id': tc.id,
                    'content': json.dumps(result, ensure_ascii=False),
                })(),
            ))

        # 将 assistant 回复和 tool 结果加入消息历史
        messages.append(Message(
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            tool_calls=response.tool_calls,
        ))
        messages.extend(tool_messages)

    # 超过最大迭代次数
    final_answer = "抱歉，数据源连接过程中遇到问题，请检查参数后重试。"
    _send_event(state, "final_result", {
        "answer": final_answer,
        "success": False,
        "datasource_id": datasource_id,
    })
    return {
        "final_answer": final_answer,
        "status": "failed",
        "datasource_id": datasource_id,
        "tables_imported": 0,
    }
```

注意：确保 `Message` 的 tool_calls 和 tool_result 参数和现有实现一致（以现有 message.py 为准）。

### Step 2: 导出节点

在 `nl2sql/agent/nodes/__init__.py` 中：
- import: `from .connect_datasource import connect_datasource_node`
- __all__: `"connect_datasource_node",`

### Step 3: 写测试

创建 `tests/test_agent/test_nodes_connect_ds.py`，用 mock LLM 测试：
- 正常流程：create → test → import → 总结
- 缺少信息时：LLM 返回纯文字（不调用工具），让用户补充
- 连接失败时：正确传递错误信息
- 最大迭代次数保护

### Step 4: 运行测试

```bash
.venv/bin/python -m pytest tests/test_agent/test_nodes_connect_ds.py -v --tb=short
```
Expected: 全部通过

### Step 5: 全量测试

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```
Expected: 全部通过

### Step 6: Commit

```bash
git add nl2sql/agent/nodes/connect_datasource.py nl2sql/agent/nodes/__init__.py tests/test_agent/test_nodes_connect_ds.py
git commit -m "feat(agent): add connect_datasource node for agentic DB onboarding"
```

---

## Task 3: Agent 图接入 + 条件路由

**Files:**
- Modify: `backend/nl2sql/agent/graph.py` — 接入 connect_datasource 分支
- Modify: `backend/app/services/chat_service.py` — 处理 connect_datasource 分支的消息保存和 final_result
- Test: 确保现有测试都通过

### Step 1: 增加条件路由函数

在 `graph.py` 中增加一个路由函数（或者在 clarify 节点的条件函数中扩展）。

最简洁的方式：新增 `route_after_clarify` 函数：

```python
def route_after_clarify(state: dict) -> str:
    """澄清后的路由判断.

    Returns:
        "ask_clarify" / "connect_datasource" / "generate_sql"
    """
    # 如果需要澄清，先走澄清
    if state.get("awaiting_clarification"):
        return "ask_clarify"
    # 根据意图 action 路由
    intent = state.get("intent")
    action = getattr(intent, "action", "query") if intent else "query"
    if action == "connect_datasource":
        return "connect_datasource"
    return "generate_sql"
```

注意：需要先检查是否需要澄清。如果 clarify 节点判断需要澄清，则走 ask_clarify；澄清完回来后再路由到对应分支。

这个路由逻辑需要和现有 clarify 流程协调好。建议：
- 保留现有 `need_clarify_conditional` 函数
- clarify 之后加一个新的 action_router 条件边
- 或者直接把 action 路由合并到 need_clarify_conditional 里

推荐方案：**修改 `need_clarify_conditional`**，让它返回三个值：`ask_clarify` / `connect_datasource` / `generate_sql`。

### Step 2: 修改图构建

在 `build_graph()` 中：

1. 增加节点：
```python
graph.add_node("connect_datasource", connect_datasource_node)
```

2. 修改条件边：把 clarify 的条件边从 2 个选项改成 3 个选项（增加 connect_datasource）

3. 增加 connect_datasource → END 的边：
```python
graph.add_edge("connect_datasource", END)
```

注意：connect_datasource 节点自己会发 final_result 事件，不需要经过 summarize 节点。

4. 更新图结构注释

### Step 3: 修改 chat_service

在 `chat_service.py` 的 `_run_chat_sync` 中，需要正确处理 connect_datasource 分支的结果：

- 从 agent.run() 返回值中检查 status 和 final_answer
- 保存助手消息（content 就是 final_answer）
- 这种类型的消息可能没有 sql 和 execution_result

检查现有 `_run_chat_sync` 代码，确保即使没有 sql 和 execution_result，add_message 也能正常工作。应该没问题，因为 sql_text 和 result 都是可选的。

### Step 4: 运行测试

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```
Expected: 全部通过

### Step 5: Commit

```bash
git add nl2sql/agent/graph.py app/services/chat_service.py
git commit -m "feat(agent): wire connect_datasource branch into agent graph"
```

---

## Task 4: 前端适配

**Files:**
- Modify: `frontend/src/lib/types.ts` — 增加事件类型、思考阶段
- Modify: `frontend/src/hooks/useSSE.ts` — 注册新事件
- Modify: `frontend/src/hooks/useChat.ts` — 处理新事件，更新阶段
- Test: tsc --noEmit + npm run build

### Step 1: 扩展类型

在 `types.ts` 中：

1. `SseEventType` 增加：
```typescript
  | 'ds_creating'
  | 'ds_created'
  | 'ds_testing'
  | 'ds_connected'
  | 'ds_connection_failed'
  | 'ds_importing'
  | 'ds_imported'
```

2. `ThinkingStage` 增加：
```typescript
  | 'connecting_datasource'
  | 'importing_schema'
```

3. `THINKING_STAGES` 数组增加：
```typescript
  { key: 'connecting_datasource', label: '连接数据源' },
  { key: 'importing_schema', label: '导入 Schema' },
```

注意位置：放在 `sql_executed` 之后、`reflection` 之前。

### Step 2: useSSE 注册事件

在 `useSSE.ts` 的 `allEvents` 数组中增加 7 个新事件类型。

### Step 3: useChat 处理事件

在 `useChat.ts` 的 `handleEvent` 中增加对 ds_* 事件的处理，更新 currentStage：

```typescript
case 'ds_creating':
case 'ds_created':
case 'ds_testing':
  setCurrentStage('connecting_datasource')
  break
case 'ds_connected':
case 'ds_importing':
  setCurrentStage('importing_schema')
  break
case 'ds_imported':
  setCurrentStage('importing_schema')
  break
```

同时确认 final_result 事件在 connect_datasource 分支下也能正确工作（把 final_answer 作为助手消息保存）。

### Step 4: 类型检查

```bash
cd frontend
npx tsc --noEmit
```
Expected: 0 errors

### Step 5: 构建验证

```bash
npm run build
```
Expected: 成功

### Step 6: Commit

```bash
git add src/lib/types.ts src/hooks/useSSE.ts src/hooks/useChat.ts
git commit -m "feat(frontend): add datasource connection events and thinking stages"
```

---

## Task 5: 集成测试 + 验证

**Files:**
- 确保所有测试通过
- 端到端验证（mock LLM）

### Step 1: 全量后端测试

```bash
cd backend
.venv/bin/python -m pytest tests/ -v --tb=short
```
Expected: 全部通过

### Step 2: 前端构建

```bash
cd frontend
npm run build
```
Expected: 成功

### Step 3: 更新后端 README（可选）

如果 README 里有功能列表，增加"自然语言添加数据源"这一项。

如果 README 没更新也没关系，不影响功能。

### Step 4: Commit (如有修改)

```bash
git add <files>
git commit -m "test: integration tests for agentic datasource management"
```
