# Langfuse 可观测性集成设计

> 为 nl2sql 项目引入 Langfuse 自部署 tracing 系统，实现全链路 LLM 调用追踪、成本分析和调试能力。

## 背景与目标

项目当前有 16 个 LLM 调用点，分布在 Dispatcher、LangGraph 节点、独立 Agent 和后台服务中。调试时无法直观看到每一步的输入输出、耗时和 token 消耗，也缺少系统的成本统计手段。

**目标**：引入 Langfuse 自部署方案，在不重构现有 LLM 抽象层的前提下，实现全链路 tracing，为调试、成本分析、prompt 迭代和用户反馈提供基础。

**非目标**（Phase 1 不做）：
- 不迁移到 LangChain ChatModel
- 不做前端用户反馈按钮（👍/👎）
- 不做 dataset/eval 功能
- 不接入 OpenTelemetry

## 集成策略

### 方案选型

| 方案 | 描述 | 结论 |
|------|------|------|
| 手动 SDK 集成 | 在 `LLMClient` 基类统一埋点 + 节点层手动创建 span | **采用** |
| LangGraph callback 集成 | 使用 langfuse.langgraph handler | 不采用：自定义 LLM 层抓不到 LLM 调用详情 |
| LangChain ChatModel 迁移 | 迁到 LangChain 模型抽象以获得自动集成 | 不采用：重构量太大，得不偿失 |
| OpenTelemetry 集成 | 通过 OTel exporter 转发 | 不采用：栈太重 |

选择手动 SDK 集成的核心理由：所有 LLM 调用都经过 `create_llm_client() → llm.chat()` 这个统一入口，在 `LLMClient` 基类做一次埋点即可覆盖全部 16 个调用点，改动最小、控制力最强。

## 系统架构

### Trace 层级模型

```
trace (一次用户提问)
  └─ span: dispatcher
       ├─ generation: classify_intent (LLM)
       └─ span: nl2sql_agent
            ├─ span: intent_analyze
            │    └─ generation: intent_analyze (LLM)
            ├─ span: intent_probe
            │    └─ generation: intent_probe (LLM + tools)
            ├─ span: query_rewrite
            │    └─ generation: query_rewrite (LLM)
            ├─ span: clarify
            │    └─ generation: clarify_check (LLM)
            ├─ span: generate_sql
            │    └─ generation: generate_sql (LLM)
            ├─ span: execute_sql        (无 LLM，纯执行)
            ├─ span: visualize
            │    └─ generation: visualize (LLM)
            ├─ span: reflect
            │    └─ generation: reflect (LLM)
            └─ span: summarize
                 └─ generation: summarize (LLM)
```

### 数据流

1. **chat_service** 收到用户提问 → 创建 trace → 注入上下文
2. **DispatcherAgent** 创建 dispatcher span → 调用子 Agent
3. **每个节点** 通过 `_step_utils` 自动创建/结束 span
4. **LLMClient.chat()** 从上下文拿到当前 span → 创建 generation → 记录输入/输出/token
5. **trace 结束** → 自动 flush 到 Langfuse 服务

## 详细设计

### 1. 配置层

**文件**：`backend/nl2sql/config.py`（`Settings` 类新增字段）

| 环境变量 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `LANGFUSE_ENABLED` | bool | `false` | 总开关，关闭时 tracing 是 no-op |
| `LANGFUSE_PUBLIC_KEY` | str | `""` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | str | `""` | Langfuse secret key |
| `LANGFUSE_HOST` | str | `"http://localhost:3030"` | Langfuse 服务地址 |

设计原则：
- **默认关闭**：不配置就是 no-op，不影响现有功能和测试
- **配置在 nl2sql 层**：因为 LLMClient 在 nl2sql 包里，tracing 模块也放 nl2sql 包里，配置跟着走

### 2. Tracing 模块

**目录**：`backend/nl2sql/tracing/`

```
tracing/
├── __init__.py          # 导出 tracer 公共 API
├── langfuse_client.py   # Langfuse 客户端单例管理
├── tracer.py            # 核心 tracer：trace/span/generation 上下文管理器
└── context.py           # contextvars 管理当前 trace/span 上下文
```

#### 2.1 langfuse_client.py

- 懒加载单例：第一次使用时根据配置初始化 `Langfuse` 客户端
- 如果 `LANGFUSE_ENABLED=false` 或 key 缺失，返回 `None`
- 提供 `get_langfuse()` 函数，调用方不需要关心是否启用

#### 2.2 context.py

基于 `contextvars.ContextVar` 管理当前活跃的 trace 和 span：

```python
current_trace: ContextVar[Optional[Any]] = ContextVar("current_trace", default=None)
current_span: ContextVar[Optional[Any]] = ContextVar("current_span", default=None)
```

- 进入 trace 时 set，退出时 reset
- 进入 span 时 set，退出时 reset 为父 span
- LLM 层通过 `current_span.get()` 拿到父级，自动嵌套

#### 2.3 tracer.py

提供三个核心上下文管理器，业务代码不直接依赖 langfuse SDK：

```python
@contextmanager
def trace(name: str, user_id: str | None = None, session_id: str | None = None,
          metadata: dict | None = None, input: Any = None) -> TraceContext:
    """创建一个 trace。如果 tracing 未启用，返回 no-op 上下文。"""

@contextmanager
def span(name: str, metadata: dict | None = None, input: Any = None) -> SpanContext:
    """创建一个 span，自动嵌套在当前 trace/span 下。"""

@contextmanager
def generation(name: str, model: str | None = None, input: Any = None,
               metadata: dict | None = None) -> GenerationContext:
    """创建一个 generation（LLM 调用），自动挂在当前 span 下。"""
```

每个 context 对象提供 `update(output=..., usage=..., ...)` 方法用于在上下文内部追加数据。

**关键设计：no-op 模式**

当 `LANGFUSE_ENABLED=false` 时，所有上下文管理器都返回空对象（有相同的 API 接口但什么都不做）。保证：
- 业务代码不需要 `if tracing_enabled:` 判断
- 零性能开销
- 测试环境不需要配置 Langfuse

### 3. LLM 层埋点

**文件**：`backend/nl2sql/llm/base.py`

使用**模板方法模式**重构 `chat()`：

```python
class LLMClient:
    def chat(self, messages: list[Message], tools: list[dict] | None = None,
             temperature: float = 0.0, max_tokens: int = 4096) -> ChatResponse:
        with tracer.generation(
            name=self._generation_name or "llm_chat",
            model=self.model,
            input=[m.model_dump() for m in messages],
            metadata={
                "temperature": temperature,
                "has_tools": tools is not None,
                "tool_count": len(tools) if tools else 0,
                "provider": self.provider,
            },
        ) as gen:
            result = self._chat_impl(messages, tools=tools,
                                     temperature=temperature, max_tokens=max_tokens)
            gen.update(
                output=result.content,
                usage=result.usage,  # {"input_tokens": int, "output_tokens": int}
                tool_calls=[tc.model_dump() for tc in result.tool_calls] if result.tool_calls else None,
            )
            return result

    def _chat_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096) -> ChatResponse:
        """子类实现实际的 LLM 调用逻辑。"""
        raise NotImplementedError
```

`chat_stream()` 同理，流式结束后再上报最终结果。

**generation name 的来源**：

引入 `_generation_name` 属性，默认为 `"llm_chat"`。调用方（节点代码）在创建 LLM client 后可以设置 `llm._generation_name = "intent_analyze"` 来标识这个调用的业务含义。

但更优雅的方式是：**通过 tracer.span 的 name 自动推导**——如果当前 span 是 `"intent_analyze"`，generation name 就用 `"intent_analyze"`。这样节点代码不需要改 LLM client，只需要创建 span 就行。

→ **采用 span name 自动推导 + 可选显式设置** 的策略。

### 4. Chat Service Trace 入口

**文件**：`backend/app/services/chat_service.py`

在 `_run_chat_sync()` 中包裹整个处理流程：

```python
def _run_chat_sync(session_id: str, user_query: str, ...):
    with tracer.trace(
        name="chat_turn",
        user_id=session.get("user_id") or session_id,
        session_id=session_id,
        metadata={
            "datasource_id": datasource_id,
            "message_id": message_id,
        },
        input=user_query,
    ) as trace_ctx:
        # 原有逻辑：build dispatcher, load history, run...
        result = dispatcher.run(...)
        trace_ctx.update(output=result.answer if result else None)
```

同时把 correction_detector 的后台 LLM 调用也包进单独的 trace（标为 background 类型）。

### 5. 节点 Span 埋点

**文件**：`backend/nl2sql/agent/nodes/_step_utils.py`

利用现有的 `step_start` / `step_complete` 机制，在其中嵌入 span 创建/结束：

```python
def step_start(state: dict, step_name: str, ...):
    # 原有 SSE 事件逻辑不变
    _emit_event(...)

    # 新增：创建 span
    span_ctx = tracer.span(name=step_name, metadata={"iteration": iteration})
    span_ctx.__enter__()
    # 把 span 存在 state 里，step_complete 时取出结束
    state.setdefault("_tracing_spans", {})[step_name] = span_ctx

def step_complete(state: dict, step_name: str, ...):
    # 原有 SSE 事件逻辑不变
    _emit_event(...)

    # 新增：结束 span
    span_ctx = state.pop("_tracing_spans", {}).pop(step_name, None)
    if span_ctx:
        span_ctx.update(output=detail)
        span_ctx.__exit__(None, None, None)
```

这样**所有使用 `_step_utils` 的节点自动获得 span 埋点**，不需要逐个节点改代码。

### 6. Dispatcher & 子 Agent Span

**文件**：`backend/nl2sql/agent/dispatcher.py`

在 `DispatcherAgent.run()` 中创建 dispatcher span，在调用各子 Agent 前创建对应子 span：

```python
def run(self, user_query: str, ...):
    with tracer.span(name="dispatcher", metadata={"intent": "..."}):
        intent = self._classify_intent(user_query)
        if intent == "query":
            with tracer.span(name="nl2sql_agent"):
                return self.nl2sql_agent.run(...)
        elif intent == "schema_exploration":
            with tracer.span(name="schema_explorer_agent"):
                return self.schema_explorer.run(...)
        ...
```

### 7. 独立 Agent 的 Span

**SchemaExplorerAgent** 和 **DatasourceConnectorAgent** 有自定义的 tool-calling 循环，需要：
- 入口处创建 span
- 每次循环的 LLM 调用已经被 LLMClient 自动捕获（generation）
- 工具调用可以用 `tracer.span(name=tool_name, metadata=tool_args)` 包裹（Phase 1 可选，先不做）

### 8. docker-compose 自部署

在 `docker-compose.yml` 新增两个服务：

```yaml
services:
  langfuse-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - langfuse-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse:
    image: langfuse/langfuse:latest
    depends_on:
      langfuse-db:
        condition: service_healthy
    ports:
      - "3030:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET:?err}
      SALT: ${LANGFUSE_SALT:?err}
      ENCRYPTION_KEY: ${LANGFUSE_ENCRYPTION_KEY:?err}

volumes:
  langfuse-db-data:
```

同时在 `Makefile` 增加：
- `make langfuse-up` — 启动 Langfuse
- `make langfuse-down` — 停止 Langfuse

## Phase 2 预留扩展点

Phase 1 不实现，但在设计中预留接口：

| 功能 | 预留方式 |
|------|----------|
| 用户反馈评分 | `tracer.score(trace_id, value, comment)` 方法 |
| 工具调用追踪 | `tracer.span()` 已支持，Phase 2 只需在工具执行处包裹 |
| SQL 执行结果 metadata | 已有 `metadata` 机制，Phase 2 往对应 span 里加 |
| Dataset 导出 | 独立服务，读取 generation_log 表或 Langfuse API |
| Eval runner | 独立服务，基于 dataset 跑评估 |

## 错误处理与降级

1. **Langfuse 服务不可达**：Langfuse SDK 自带重试和本地队列，不会阻塞业务流程。如果彻底不可用，数据会丢失但不影响用户体验。
2. **网络异常**：SDK 异步 flush，不阻塞主线程。
3. **配置缺失**：直接进入 no-op 模式，等于 tracing 关闭。
4. **flush 保证**：在 `chat_service` 结束 trace 后调用 `langfuse.flush()` 一次，确保数据发出去（可选，不强制）。

## 测试策略

### 单元测试
- `test_tracer_noop.py` — 验证禁用时 tracer 是 no-op，不抛异常
- `test_tracer_context.py` — 验证 trace/span/generation 嵌套关系正确（用 mock langfuse client）
- `test_llm_client_tracing.py` — 验证 LLMClient.chat() 正确创建 generation 并记录 input/output/usage

### 集成测试
- 不需要真实 Langfuse 服务，用 mock 验证调用链
- 已有测试全部保持通过（tracing 默认关闭）

### 手动验证
- 启动 Langfuse + 后端，发送一条查询，在 Langfuse UI 中检查：
  - trace 是否创建
  - span 层级是否正确
  - generation 输入输出是否完整
  - token 计数是否准确

## 对现有代码的影响

| 模块 | 改动类型 | 说明 |
|------|----------|------|
| `nl2sql/config.py` | 新增 | 加 4 个配置字段 |
| `nl2sql/tracing/` | 新增 | 约 200 行新代码 |
| `nl2sql/llm/base.py` | 修改 | 模板方法重构 + 埋点，约 +30 行 |
| `nl2sql/llm/claude_client.py` | 修改 | `chat()` → `_chat_impl()` 重命名 |
| `nl2sql/llm/openai_client.py` | 修改 | `chat()` → `_chat_impl()` 重命名 |
| `nl2sql/agent/nodes/_step_utils.py` | 修改 | step_start/complete 加 span 逻辑 |
| `nl2sql/agent/dispatcher.py` | 修改 | run() 加 dispatcher span + 子 Agent span |
| `app/services/chat_service.py` | 修改 | 加 trace 包裹 |
| `docker-compose.yml` | 新增 | langfuse + postgres 服务 |
| `Makefile` | 新增 | langfuse-up/down 命令 |
| `pyproject.toml` | 新增 | `langfuse` 依赖 |

**破坏性变更：无**。所有改动都是增量的，默认配置下行为完全不变。
