# Langfuse 可观测性集成 — 深度技术文档

> 面向架构师和高级工程师的深度技术解析：设计决策、实现细节、踩坑记录与运维指南。
>
> 版本：v1.0 | 日期：2026-09-01 | 分支：`feature/langfuse-observability`

---

## 目录

1. [架构总览](#1-架构总览)
2. [核心设计决策](#2-核心设计决策)
3. [Tracing 模块实现](#3-tracing-模块实现)
4. [LLM 层埋点](#4-llm-层埋点)
5. [Agent 层集成](#5-agent-层集成)
6. [Chat Service 入口](#6-chat-service-入口)
7. [配置与部署](#7-配置与部署)
8. [踩坑记录](#8-踩坑记录)
9. [验证与测试](#9-验证与测试)
10. [未来扩展](#10-未来扩展)

---

## 1. 架构总览

### 1.1 为什么需要 Langfuse

项目中分布着 **16+ 个 LLM 调用点**，跨 Dispatcher、LangGraph 节点（intent/generate/reflect/summarize/visualize/clarify/rewrite）、Schema Explorer Agent、Datasource Connector Agent 和后台纠错检测服务。调试时面临以下痛点：

- **黑盒**：不知道某个 query 走了哪些节点、每步的输入输出是什么
- **不可量化**：每个 query 的 token 消耗、成本、延迟无法统计
- **难复现**：线上出问题时，不知道当时的 prompt 和模型输出
- **无法迭代**：prompt 优化效果无法量化对比

Langfuse 提供了 trace/span/generation 三级观测模型，正好匹配我们的 Agent 架构。

### 1.2 Trace 层级模型

```
trace (chat_turn)                          ← 顶层：一次用户提问
  └─ span: dispatcher                       ← 分发器
       ├─ generation: classify_intent       ← 意图分类 LLM 调用
       └─ span: nl2sql_agent                ← NL2SQL 子 Agent
            ├─ span: intent_analyze
            │    └─ generation: intent_analyze
            ├─ span: intent_probe
            │    └─ generation: intent_probe (tools)
            ├─ span: query_rewrite
            │    └─ generation: query_rewrite
            ├─ span: clarify
            │    └─ generation: clarify_check
            ├─ span: generate_sql
            │    └─ generation: generate_sql
            ├─ span: execute_sql             ← 纯执行，无 LLM
            ├─ span: visualize
            │    └─ generation: visualize
            ├─ span: reflect
            │    └─ generation: reflect
            └─ span: summarize
                 └─ generation: summarize
```

### 1.3 数据流

```
用户请求 → chat_service 创建 trace → 注入 contextvars
                ↓
         dispatcher 创建 span
                ↓
         各节点通过 step_utils 自动创建/结束 span
                ↓
         LLMClient.chat() 从 contextvars 读当前 span → 创建 generation
                ↓
         trace 结束 → chat_service flush → Langfuse 服务
```

---

## 2. 核心设计决策

### 2.1 方案选型：手动 SDK vs LangGraph Callback vs LangChain 迁移

| 方案 | 改动量 | LLM 调用覆盖 | 调试灵活性 | 结论 |
|------|--------|-------------|-----------|------|
| **手动 SDK 集成** | 中（~500行） | 100%（LLMClient 基类统一埋点） | 高 | ✅ 采用 |
| LangGraph callback | 小 | 低（只能看到节点，看不到 LLM 详情） | 低 | ❌ |
| 迁到 LangChain ChatModel | 大（重构全部 LLM 客户端） | 高 | 低 | ❌ |
| OpenTelemetry | 大 | 中 | 中 | ❌ |

**核心理由**：所有 LLM 调用都经过 `create_llm_client() → llm.chat()` 这个统一入口。在基类做一次埋点，所有子类自动获得 tracing 能力，改动最小、控制力最强。

### 2.2 No-op 模式设计原则

**默认开启，缺 key 时静默降级**。这是一个关键的设计决策：

- `LANGFUSE_ENABLED=true`（默认开启）
- 但默认 `LANGFUSE_PUBLIC_KEY=""` 和 `LANGFUSE_SECRET_KEY=""`
- 缺 key 时，`get_langfuse()` 返回 `None`，所有 trace/span/generation 都是 no-op

这样做的好处：
- **新环境零配置**：不需要为了不报错而显式关闭
- **部署即启用**：只要配置了 key，立刻有 tracing
- **零性能开销**：no-op 模式下只有一次函数调用和 None 判断

### 2.3 ContextVars vs ThreadLocal

选择 `contextvars.ContextVar` 而不是 `threading.local`：

| 特性 | contextvars | threading.local |
|------|------------|-----------------|
| 线程安全 | ✅ | ✅ |
| asyncio 安全 | ✅ | ❌ |
| 上下文管理器自动恢复 | ✅（token 机制） | ❌（手动管理） |
| Python 版本 | 3.7+ | 全版本 |

虽然当前后端是同步的（FastAPI + 后台线程），但用 contextvars 为未来的 async 改造留了余地。而且 contextvars 的 token 机制和上下文管理器天然契合，进入时 set、退出时 reset，干净利落。

### 2.4 为什么不直接依赖 langfuse SDK

整个 tracing 模块有一个**严格的边界**：

- 业务代码（LLMClient、节点、chat_service）**只 import `nl2sql.tracing`**
- 只有 `langfuse_client.py` 直接 import `langfuse` 包
- tracing 模块导出的所有 API 在 no-op 模式下都有相同的签名

这样做的价值：
- **可替换**：以后换成其他 tracing 后端（如 LangSmith、Helicone），只改 tracing 模块
- **可测试**：测试时不需要安装 langfuse 包
- **编译时安全**：没有 langfuse 包时，整个应用也能正常跑

---

## 3. Tracing 模块实现

### 3.1 模块结构

```
nl2sql/tracing/
├── __init__.py          # 公共 API 导出
├── langfuse_client.py   # Langfuse 客户端单例 + 优雅降级
├── tracer.py            # 核心：trace/span/generation 上下文管理器
└── context.py           # contextvars 上下文管理
```

### 3.2 langfuse_client.py — 三级优雅降级

```python
def get_langfuse() -> Langfuse | None:
    # 第 1 级：总开关关闭 → None
    if not settings.langfuse_enabled:
        return None

    # 第 2 级：key 缺失 → None
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    # 第 3 级：导入或初始化失败 → None
    try:
        from langfuse import Langfuse
        return Langfuse(public_key=..., secret_key=..., host=...)
    except Exception:
        return None
```

单例模式 + 懒加载：第一次调用时初始化，之后复用。

### 3.3 context.py — 上下文存储

两个 ContextVar：

- `_current_trace`：当前活跃的 trace 对象
- `_current_span`：当前活跃的 span 对象

为什么区分 trace 和 span？因为：
- **span 可以嵌套**（span 里面创建 span，父 span 是当前 span）
- **trace 只有一个**（每个 trace 的顶层 span 的 parent 是 trace）
- generation 的 parent 优先级：当前 span > 当前 trace > 不创建

### 3.4 tracer.py — 上下文管理器设计

三种上下文管理器，API 形状完全一致：

```python
# Trace
with trace(name="chat_turn", user_id=..., input=...) as trace_ctx:
    trace_ctx.update(output=..., metadata=...)

# Span
with span(name="generate_sql", input=...) as span_ctx:
    span_ctx.update(output=..., metadata=...)

# Generation
with generation(name="generate_sql", model="glm-5.3", input=...) as gen_ctx:
    gen_ctx.update(output=..., usage={...}, tool_calls=[...])
```

每个 context 对象提供：
- `.id` 属性：获取 Langfuse 端的 ID
- `.update(**kwargs)` 方法：追加数据
- `.score()` 方法：评分（Phase 2 用户反馈预留）

#### No-op 上下文

`_NoopContext` 类有完全相同的 API，但什么都不做。这样业务代码里不需要 `if tracing_enabled:` 判断。

#### 关键实现细节：span 的自动嵌套

```python
parent = ctx.get_current_span() or ctx.get_current_trace()
if parent is None:
    yield _NoopContext()
    return

span_obj = parent.span(**kwargs)  # 挂在当前 span/trace 下
token = ctx.set_current_span(span_obj)
try:
    yield span_ctx
finally:
    span_obj.end()
    ctx.reset_current_span(token)  # 恢复为父 span
```

进入 span 时设置 `current_span`，退出时恢复。这样嵌套的 span 自动形成正确的层级。

generation 不修改 `current_span`，因为它是叶子节点，不会有子 span。

### 3.5 Usage 格式的坑（v2 SDK）

**重要**：Langfuse v2 Python SDK 的 `usage` 字段格式是 **驼峰命名**：

```python
# 正确格式（v2 SDK）
{
    "promptTokens": 100,
    "completionTokens": 50,
    "totalTokens": 150,  # 可选
}

# 错误格式（会抛 ValueError）
{
    "input_tokens": 100,   # ❌
    "output_tokens": 50,   # ❌
    "total_tokens": 150,   # ❌
}
```

这是实现过程中发现的关键 bug。`tracer.py` 中的 `_GenerationContext.update()` 会做自动归一化：

- `input_tokens` / `prompt_tokens` → `promptTokens`
- `output_tokens` / `completion_tokens` → `completionTokens`
- `total_tokens` → `totalTokens`
- 如果有 input + output 但没有 total，自动计算 total

---

## 4. LLM 层埋点

### 4.1 模板方法模式

`LLMClient` 基类的 `chat()` 方法是模板方法：

```
chat() [基类]
  ├─ 创建 generation (tracing)
  ├─ 调用 _chat_impl() [子类实现]
  └─ 记录 output + usage + tool_calls (tracing)
```

子类只需要实现 `_chat_impl()` 和 `_chat_stream_impl()`，自动获得 tracing 能力。

### 4.2 流式调用的特殊处理

`chat_stream()` 不能直接在上下文管理器里 yield 完就结束——因为流式结束后才知道完整的输出和 usage。

实现方式：
1. 进入 generation 上下文
2. 迭代所有 chunk，一边 yield 一边收集
3. 迭代结束后，从 chunks 中拼装完整 content 和 tool_calls
4. 调用 `gen_ctx.update()` 记录最终结果
5. 退出上下文（自动 end generation）

代价是内存中会保留一份完整的 chunks 列表。对于普通对话（几千 token）完全不是问题，但超长生成可能需要考虑优化。

### 4.3 Generation Name 自动推导

generation 的 name 标识这个 LLM 调用的业务含义（在 Langfuse UI 中显示）。

三级优先级：
1. **显式设置**：`llm.set_generation_name("intent_analyze")` — 最高优先级
2. **当前 span 名称**：如果当前有活跃的 span，用 span 的 name — 最常用
3. **默认 fallback**：`"llm_chat"` — 兜底

这样设计的好处是：**节点代码几乎不需要改**。只要节点创建了 span，里面的 LLM 调用自动以 span 名称作为 generation 名称。

---

## 5. Agent 层集成

### 5.1 _step_utils.py — SSE 事件 + Tracing 二合一

这是一个很漂亮的设计：`step_start` / `step_complete` / `step_error` 同时做两件事：
1. 发送 SSE 事件（给前端展示进度）
2. 创建/结束 Langfuse span（给 tracing）

业务代码只需要调用一次，两个功能都有了。

#### Tracing 的懒导入

```python
def _get_tracer():
    try:
        from nl2sql.tracing import tracer
        return tracer
    except Exception:
        return None
```

不在模块顶部 import，而是用到时才导入。这样即使 tracing 模块有问题（比如 langfuse 包没装），也不影响 SSE 事件功能。

#### Span 的存储与生命周期

Span 对象存在 `state["_tracing_spans"]` 字典里：
- `step_start` 时 `__enter__()` 创建 span，存入 state
- `step_complete` 时从 state 取出，`update()` + `__exit__()` 结束 span
- `step_error` 时同理，附带 error metadata

为什么存在 state 里而不是 contextvars？因为 LangGraph 的节点是函数调用，进入和退出不在同一个上下文管理器的词法作用域里。LangGraph 负责调用节点函数，我们只能在函数开始和结束时手动管理 span。

**所有 tracing 异常都被静默吞掉**——tracing 永远不能影响业务流程。

### 5.2 Dispatcher 层

`DispatcherAgent.run()` 中：

```python
with _tracing_span(name="dispatcher", metadata={"user_query": user_query}) as disp_span:
    intent = self._classify_intent(user_query, conversation_history)
    disp_span.update(metadata={
        "intent": intent["intent"],
        "confidence": intent.get("confidence"),
        "reasoning": intent.get("reasoning", "")[:200],
    })

    if intent["intent"] == "query":
        with _tracing_span(name="nl2sql_agent"):
            return self.nl2sql_agent.run(...)
    elif intent["intent"] == "schema_exploration":
        with _tracing_span(name="schema_explorer_agent"):
            return self.schema_explorer.run(...)
    ...
```

这里体现了两个设计点：
- **dispatcher span 的 metadata 延迟填充**：分类完成后才知道 intent，所以先创建 span，分类完再 update
- **子 Agent 各自有独立的 span**：nl2sql_agent、schema_explorer_agent 等，层级清晰

---

## 6. Chat Service 入口

`_run_chat_sync()` 是整个 tracing 的顶层入口。

### 6.1 Trace 创建参数

```python
with _tracing_trace(
    name="chat_turn",
    user_id=session.get("user_id") or session_id,
    session_id=session_id,
    metadata={
        "datasource_id": datasource_id,
        "message_id": message_id,
        "project_id": project_id,
    },
    input=user_query,
) as trace_ctx:
```

- `user_id`：用 session_id 兜底（匿名用户）
- `session_id`：会话 ID，用于在 Langfuse 中追踪多轮对话
- `metadata`：携带业务关联信息，方便后续筛选

### 6.2 成功/失败都更新

**成功路径**：更新 output + metadata（status, success, sql, iteration, intent_type, execution_time_ms）

**失败路径**：更新 metadata（error, traceback）

无论成功失败，trace 都会被记录。这对于调试非常重要——失败的 query 反而更需要 trace。

### 6.3 Trace ID 回传

```python
result_data["trace_id"] = trace_ctx.id
```

trace_id 存入结果，通过 SSE 的 `chat_done` 事件传给前端。前端可以用这个 ID 拼接 Langfuse UI 的跳转链接，方便用户一键跳转到对应的 trace。

### 6.4 Flush 保证

```python
finally:
    _tracing_flush()
```

`finally` 块中强制 flush，确保 trace 数据在请求结束前发送出去。Langfuse SDK 默认是异步批量发送的，如果不 flush，数据可能在队列里等几秒才发。

对于我们的场景（每次 query 独立 trace），flush 是合理的——延迟增加几十毫秒，但换来数据立即可见。

---

## 7. 配置与部署

### 7.1 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LANGFUSE_ENABLED` | `true` | 总开关（关闭后完全 no-op） |
| `LANGFUSE_PUBLIC_KEY` | `""` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `""` | Langfuse secret key |
| `LANGFUSE_HOST` | `"http://localhost:3030"` | Langfuse 服务地址 |

配置放在 `nl2sql/config.py` 的 `Settings` 类中，和其他配置一样走 pydantic-settings。

### 7.2 Docker Compose 部署

两个服务：
- `langfuse-db`：Postgres 16（Langfuse 的元数据库）
- `langfuse`：Langfuse v2 镜像（端口 3030 → 3000）

选择 v2 而不是 v3 的原因：v3 需要额外部署 ClickHouse，更重。v2 只需要 Postgres，对于我们的规模（几十到几百 QPS）完全够用。

### 7.3 一键初始化

`scripts/setup-langfuse.sh` 脚本：
1. 启动 Langfuse 容器
2. 等待服务就绪
3. 调用 `langfuse-init.sh` 自动创建管理员账号、项目、API Key
4. 把 API Key 写入 `.env` 文件

这样新环境只需要跑一条命令就能用 Langfuse。

---

## 8. 踩坑记录

### 8.1 ❌ Usage 格式错误（ValueError）

**现象**：LLM 调用时 tracing 抛出 `ValueError: Usage object must have either {input, output, total, unit} or {promptTokens, completionTokens, totalTokens}`

**原因**：Langfuse v2 Python SDK 的 usage 字段是驼峰命名（`promptTokens`/`completionTokens`），但我们传的是蛇形（`input_tokens`/`output_tokens`）。

**修复**：`_GenerationContext.update()` 中做自动归一化，蛇形→驼峰转换。

**教训**：不要想当然地猜 API 格式，一定要看 SDK 源码或文档验证。

### 8.2 ❌ macOS 系统代理导致 502 Bad Gateway

**现象**：curl 调用 Langfuse API 正常，但 Python 的 httpx/urllib/langfuse-sdk 全部返回 502。

**原因**：macOS 开了全局代理（Clash/ Surge 等），Python 进程读取系统代理设置，但代理对 `localhost` 的转发有问题。curl 也读代理，但它正确处理了 macOS 的 `ExceptionsList`（`localhost` 在例外列表里），Python 的 `urllib.request.getproxies()` 不处理例外列表。

**修复**：启动后端时设置环境变量 `NO_PROXY=localhost,127.0.0.1`。

**教训**：本地开发环境的代理设置可能造成诡异的网络问题，排障时一定要考虑。

### 8.3 ❌ Docker Desktop 频繁挂掉

**现象**：每隔 60-90 分钟 Docker 就断了，`docker info` 连不上 daemon。

**原因**：内存不足导致 macOS 杀掉了 `com.docker.backend` 进程。Dify + nl2sql 两套系统 18 个容器，VM 配 8GB，加上宿主机的一堆 Electron 应用（飞书、WPS、Claude 等），内存压力太大。

**修复**：停掉不用的 Dify 容器，释放约 2.5GB 内存。

**教训**：开发环境也要注意资源管理，容器不是免费的。

### 8.4 ⚠️ Langfuse SDK 的异步 flush

`langfuse.flush()` 可能阻塞很久（默认重试次数多，每次超时 20 秒）。如果 Langfuse 服务不可达，flush 会卡住。

目前我们在 `finally` 块里调用 flush，如果 Langfuse 挂了可能增加请求延迟。可以考虑：
- 设置 `timeout` 和 `max_retries` 参数
- 或者不在请求线程里 flush，交给后台定时刷

目前因为开发阶段、Langfuse 就在本地，暂时不是问题。

---

## 9. 验证与测试

### 9.1 单元测试

`tests/test_tracing/` 目录下 9 个测试文件：

| 测试文件 | 覆盖内容 |
|----------|---------|
| `test_langfuse_client.py` | 单例、降级逻辑 |
| `test_tracer_noop.py` | no-op 模式不报错、上下文清理 |
| `test_tracer_mock.py` | mock 模式下的嵌套行为 |
| `test_context.py` | contextvars 管理 |
| `test_llm_tracing.py` | LLM 基类 tracing 集成 |
| `test_dispatcher_tracing.py` | Dispatcher span 集成 |
| `test_step_utils_tracing.py` | step_start/complete/error |
| `test_chat_service_tracing.py` | chat_service trace 入口 |
| `test_e2e_tracing.py` | 全链路 mock 测试 |

### 9.2 E2E 测试

`tests/e2e_langfuse_tracing.py`：需要真实 Langfuse 服务，验证完整数据链路。

### 9.3 手动验证清单

启动 Langfuse + 后端，发送一条查询，在 Langfuse UI 中检查：

- [ ] trace 是否创建，name 是 `chat_turn`
- [ ] input/output 是否正确
- [ ] session_id / user_id 是否正确
- [ ] metadata（datasource_id, sql 等）是否完整
- [ ] span 层级是否正确（dispatcher → nl2sql_agent → 各节点）
- [ ] generation 是否有完整的 input/output/usage
- [ ] token 计数是否准确
- [ ] 错误场景是否也有 trace

### 9.4 本次 E2E 验证结果

✅ **17 个 observations**（dispatcher + nl2sql_agent + intent/intent_probe/generate_sql/execute_sql/visualize/reflect/summarize 等节点 span + LLM generation）全部正确上报。

---

## 10. 未来扩展

### Phase 2 预留功能

| 功能 | 预留方式 | 实现难度 |
|------|----------|---------|
| 用户反馈评分 | `_TraceContext.score()` 方法已实现 | 低 |
| 工具调用追踪 | `tracer.span()` 已支持，在工具执行处包裹即可 | 低 |
| SQL 执行结果 metadata | 已有 metadata 机制，在 execute 节点追加 | 低 |
| Dataset 导出 | 独立服务，读 generation_log 或 Langfuse API | 中 |
| Eval runner | 基于 dataset 跑评估 | 中 |
| 前端 trace 跳转按钮 | 从 SSE 的 chat_done 事件取 trace_id | 低 |
| OpenTelemetry 集成 | 通过 Langfuse OTel exporter 转发 | 高 |

### 潜在优化

1. **批量 flush 调优**：调整 SDK 的 `flush_at` 和 `flush_interval`，平衡延迟和吞吐量
2. **采样率**：高流量时可以设置 `sample_rate`，只追踪部分请求
3. **敏感数据脱敏**：`langfuse` SDK 支持 `mask` 函数，可以脱敏 prompt 中的敏感信息
4. **多环境隔离**：用 `environment` 参数区分 dev/staging/prod 的 trace

---

## 附录：关键文件索引

| 文件 | 作用 | 行数 |
|------|------|------|
| `nl2sql/tracing/__init__.py` | 公共 API | 6 |
| `nl2sql/tracing/langfuse_client.py` | 客户端单例 + 降级 | 67 |
| `nl2sql/tracing/tracer.py` | 核心上下文管理器 | 258 |
| `nl2sql/tracing/context.py` | contextvars 管理 | 43 |
| `nl2sql/llm/base.py` | LLM 基类埋点（模板方法） | 179 |
| `nl2sql/agent/dispatcher.py` | Dispatcher span | +~20 行 |
| `nl2sql/agent/nodes/_step_utils.py` | 节点 span（SSE + tracing） | 186 |
| `app/services/chat_service.py` | Trace 入口 + flush | +~50 行 |
| `nl2sql/config.py` | 4 个新增配置字段 | +4 行 |

**总新增代码量**：约 500 行（tracing 模块 ~375 行 + 各集成点 ~125 行）

---

*文档结束。如有疑问，查看 git history 或联系开发团队。*
