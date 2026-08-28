# Langfuse 可观测性集成 — 技术报告

> 项目：AskSql（NL2SQL AI 数据查询工具）
> 功能：Langfuse 全链路 LLM 调用追踪
> 周期：1 周（10 个任务，11 次提交）

---

## 一、项目背景

### 1.1 问题

AskSql 是一个基于 LangGraph 多 Agent 架构的自然语言转 SQL 工具。随着 Agent 链路越来越复杂（分发 → 意图识别 → SQL 生成 → 反思 → 执行 → 总结），团队面临以下痛点：

- **调试困难**：一次用户查询涉及 5+ 次 LLM 调用，出错时无法快速定位是哪个节点、哪次调用出了问题
- **成本不透明**：无法按用户、会话、查询类型统计 token 消耗，成本估算靠猜
- **性能无数据**：各节点耗时分布不清楚，优化没有方向
- **质量难量化**：没有追踪数据支撑，无法做 A/B 测试和质量回归分析

### 1.2 选型

在对比了 LangSmith、Langfuse、自建方案后，选择 **Langfuse**：

| 维度 | Langfuse | LangSmith | 自建 |
|------|----------|-----------|------|
| 开源自托管 | ✅ MIT | ❌ 闭源 SaaS | ✅ 但工作量大 |
| 成本 | 免费（自托管） | 按 token 收费 | 服务器成本 |
| UI 完整度 | ✅ Trace/span/dashboard | ✅ 非常成熟 | ❌ 需要自己做 |
| SDK 成熟度 | ✅ Python/JS | ✅ 最成熟 | — |
| 数据隐私 | ✅ 数据不出域 | ❌ 数据外传 | ✅ |

**结论**：Langfuse 自托管方案，功能足够、成本可控、数据安全。

---

## 二、架构设计

### 2.1 设计原则

1. **可插拔**：默认关闭，零性能影响
2. **优雅降级**：配置缺失 / SDK 导入失败 / 网络异常 — 一律静默降级为 no-op，绝不影响主流程
3. **低侵入**：业务代码只调用 `trace/span/generation` 三个 context manager，不直接依赖 langfuse SDK
4. **自动传播**：使用 contextvars 管理 trace/span 上下文，跨函数、跨模块自动传递

### 2.2 Trace 结构

一次用户查询产生一条完整的调用树：

```
Trace: chat_turn                                ← 顶层（chat_service 入口）
  ├── user_id / session_id / datasource_id
  ├── input: 用户问题
  ├── output: 最终回答
  │
  └── Span: dispatcher                          ← 分发层
        ├── intent / confidence
        │
        └── Span: nl2sql_agent                  ← 子 Agent（query 路径）
              │
              ├── Span: intent_analyze          ← 节点 1：意图分析
              │     └── Generation: llm_chat    ← LLM 调用
              │           ├── model / input / output
              │           └── usage (input_tokens / output_tokens)
              │
              ├── Span: sql_generation          ← 节点 2：SQL 生成
              │     └── Generation: llm_chat
              │
              ├── Span: sql_reflection          ← 节点 3：反思修正
              │     └── Generation: llm_chat
              │
              └── ...
```

三级结构对应 Langfuse 的核心概念：
- **Trace**：一次完整的用户交互（顶层单元）
- **Span**：一个操作步骤（可以嵌套）
- **Generation**：一次 LLM 调用（叶子节点，带 model 和 usage）

### 2.3 模块划分

```
nl2sql/tracing/
├── __init__.py           # 公开 API: trace / span / generation / flush
├── langfuse_client.py    # Langfuse SDK 单例 + 优雅降级
├── context.py            # contextvars 上下文管理（trace/span 传播）
└── tracer.py             # 核心：3 个 context manager + no-op fallback
```

**集成点**（侵入业务代码的位置，共 4 处）：

| 层 | 文件 | 改动 |
|----|------|------|
| LLM 层 | `llm/base.py` | 模板方法重构：`chat()` 包装 `_chat_impl()`，自动创建 generation |
| 节点层 | `agent/nodes/_step_utils.py` | `step_start/step_complete` 内自动创建/结束 span |
| 分发层 | `agent/dispatcher.py` | `run()` 外包 dispatcher span，子 Agent 外包对应 span |
| 服务层 | `app/services/chat_service.py` | `_run_chat_sync()` 外包 trace，记录 metadata，finally 中 flush |

---

## 三、核心技术点

### 3.1 优雅降级的三层保护

```python
def get_langfuse() -> Langfuse | None:
    # 第 1 层：开关检查（默认关闭）
    if not settings.langfuse_enabled:
        return None

    # 第 2 层：配置检查（有开关但没配 key）
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    # 第 3 层：异常兜底（SDK 导入失败或初始化失败）
    try:
        from langfuse import Langfuse
        _client = Langfuse(...)
    except Exception:
        return None
```

三种场景全部静默降级，业务代码零感知。

### 3.2 模板方法模式 + 自动追踪

**改动前**：每个 LLM 客户端各自实现 `chat()`，要加 tracing 得每个客户端都改。

**改动后**：基类 `LLMClient.chat()` 是模板方法，子类只实现 `_chat_impl()`：

```python
class LLMClient(ABC):
    def chat(self, messages, ...):
        # 统一的 tracing 逻辑（所有子类自动获得）
        with _tracing_generation(name=gen_name, model=self.model, input=...):
            result = self._chat_impl(messages, ...)
            # 记录 output 和 usage
            gen_ctx.update(output=result.content, usage=result.usage, model=result.model)
            return result

    @abstractmethod
    def _chat_impl(self, messages, ...):
        ...
```

**收益**：新增任何 LLM 供应商（Claude / OpenAI / 本地兼容），自动获得 tracing 能力，零额外代码。

### 3.3 Contextvars 上下文传播

为什么不用函数参数传递？因为调用栈太深了（chat_service → dispatcher → agent → node → llm），每一层都传 trace 对象太侵入。

用 `contextvars.ContextVar`：

```python
# context.py
_current_trace: ContextVar[Any] = ContextVar("current_trace", default=None)
_current_span: ContextVar[Any] = ContextVar("current_span", default=None)
```

context manager enter 时 set，exit 时 reset，天然支持嵌套。无论是同步还是异步（每个 task 有独立的 contextvar 副本），都正确。

### 3.4 Usage 归一化

不同 LLM 供应商返回的 token 字段名不一致：
- Anthropic：`input_tokens` / `output_tokens`
- OpenAI：`prompt_tokens` / `completion_tokens`

在 `_GenerationContext.update()` 中统一归一化为 Langfuse 的标准格式：

```python
if "input_tokens" in usage:
    langfuse_usage["input_tokens"] = usage["input_tokens"]
elif "prompt_tokens" in usage:
    langfuse_usage["input_tokens"] = usage["prompt_tokens"]
```

这样在 Langfuse UI 中所有调用的 token 统计是一致的。

### 3.5 延迟导入（Lazy Import）

`_step_utils.py` 中的 tracer 用延迟导入：

```python
def _get_tracer():
    try:
        from nl2sql.tracing import tracer as _tracing_module
        return _tracing_module
    except ImportError:
        return None
```

好处：即使 tracing 模块因为某种原因不可用，Agent 核心流程也不会崩。防御性编程。

---

## 四、测试策略

### 4.1 测试金字塔

```
        ▲
       ╱ ╲      E2E 集成测试（5 个）—— 验证完整链路和跨层集成
      ╱   ╲
     ╱ 集成 ╲    模块集成测试（7 个）—— dispatcher / chat_service / step_utils
    ╱       ╲
   ╱  单元测试 ╲   单元测试（21 个）—— client / context / tracer / llm
  ╱           ╲
 ───────────────
```

### 4.2 Mock 策略

为了在不依赖真实 Langfuse 服务的情况下验证追踪逻辑，使用 Mock Langfuse Client：

```python
class _MockLangfuse:
    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name"))
        self.traces.append(t)
        return t

class _MockSpan:
    _children = []      # 记录子 span / generation
    _updates = []       # 记录 update() 调用参数
    _ended = False      # 记录 end() 是否被调用

    def span(self, **kwargs): ...
    def generation(self, **kwargs): ...
```

测试时通过 `lc._client = mock_client` 注入 mock，然后断言：
- trace/span/generation 的数量和嵌套关系
- metadata、usage 等字段的正确性
- span 是否正确 `end()`

### 4.3 测试用例总览（33 个测试，1368 行测试代码）

| 测试文件 | 数量 | 覆盖范围 |
|---------|------|---------|
| `test_langfuse_client.py` | 2 | 默认禁用 / 缺 key 降级 |
| `test_context.py` | 5 | contextvars set/reset/stacking |
| `test_tracer_noop.py` | 4 | 禁用时所有 context manager 是 no-op |
| `test_tracer_mock.py` | 6 | trace/span/generation 嵌套 + usage 归一化 |
| `test_llm_tracing.py` | 3 | LLMClient 模板方法 + generation 自动创建 |
| `test_step_utils_tracing.py` | 5 | step_start/complete 对应 span 的创建/结束/更新 |
| `test_dispatcher_tracing.py` | 2 | dispatcher span 在 trace 内正确创建 |
| `test_chat_service_tracing.py` | 1 | chat_service 创建 trace 并填充 metadata |
| **`test_e2e_tracing.py`** | **5** | **端到端全链路 + 错误路径 + flush + 零开销验证** |

### 4.4 关键 E2E 场景

1. **chat_service → dispatcher 跨层集成**：验证 trace metadata（session_id, datasource_id, user_id, project_id）正确传递，dispatcher span 在 trace 内创建，intent/confidence 正确更新
2. **完整四级嵌套结构**：手动模拟 `trace → dispatcher → nl2sql_agent → node spans → generations` 全链路，验证每一层的父子关系、span 结束状态、generation usage 归一化
3. **默认禁用零开销**：验证默认配置下 `get_langfuse()` 返回 None，所有 context manager 是 no-op
4. **自动 flush**：验证每次 chat turn 结束后调用 flush
5. **异常路径**：验证 Agent 抛出异常时，trace 捕获 error message 和 traceback，主流程不崩溃

---

## 五、部署方案

### 5.1 Docker Compose 一键启动

```yaml
# docker-compose.yml 新增两个服务
langfuse-db:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: langfuse
    POSTGRES_USER: langfuse
    POSTGRES_PASSWORD: langfuse_secret

langfuse:
  image: langfuse/langfuse:latest
  ports:
    - "3030:3030"
  depends_on:
    langfuse-db:
      condition: service_healthy
```

### 5.2 Make 命令

```bash
make langfuse-up     # 启动 Langfuse（UI: http://localhost:3030）
make langfuse-down   # 停止
make langfuse-logs   # 查看日志
```

### 5.3 配置项

```env
# .env 中添加 4 个变量
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3030
```

使用流程：
1. `make langfuse-up` 启动服务
2. 访问 http://localhost:3030 创建管理员账号和项目
3. 拿到 public_key / secret_key 填入 `.env`
4. 设置 `LANGFUSE_ENABLED=true`
5. 重启后端，开始追踪

---

## 六、代码统计

| 维度 | 数据 |
|------|------|
| 提交次数 | 11 次 |
| 改动文件 | 27 个 |
| 新增代码 | 2,546 行 |
| 删除代码 | 271 行 |
| 核心模块代码 | 370 行（tracing/ 目录） |
| 测试代码 | 1,368 行（8 个测试文件） |
| 测试数量 | 33 个（全部通过） |
| 总测试数 | 555 个（0 回归） |

---

## 七、设计亮点与经验

### 7.1 亮点

1. **真正的可插拔**：不是"加个 if 判断"那种，而是从模块导入到 context manager 返回值全链路 no-op。默认关闭时对性能零影响
2. **模板方法模式的运用**：一次改动，所有 LLM 客户端自动获得 tracing 能力。扩展性好 — 未来加新的供应商不用改 tracing 代码
3. **优雅降级的三层防护**：开关 → 配置 → 异常，每一层都可能触发降级，但业务代码永远不会因为 tracing 出问题
4. **测试完整性**：从单元到集成到 E2E，每一层都有对应的测试。Mock 策略设计合理，可以在没有真实 Langfuse 服务的情况下验证全链路逻辑

### 7.2 可迁移经验

- **给可观测性模块做 SDK 抽象**：不要让业务代码直接依赖第三方 SDK。包一层自己的 API，未来换方案（比如换成 LangSmith 或自研）只需改一个模块
- **contextvars 是做跨层上下文传播的利器**：比函数传参清爽，比全局变量安全（异步/协程友好）
- **TDD 做基础模块效率很高**：tracing 模块的核心逻辑（context manager + mock client）用 TDD 方式开发，写完测试基本就写完了实现
- **子 Agent 开发模式适合模块化任务**：10 个任务分给 sub-agent 执行，每个任务独立开发 + 测试 + 提交，主线程只做协调和集成验证

### 7.3 未来可扩展方向

1. **得分（Score）**：在用户反馈/纠错时调用 `trace.score()`，记录查询质量评分，用于质量分析
2. **Prompt 管理**：Langfuse 支持 prompt 版本管理，可以把系统 prompt 迁过去
3. **Langfuse Decorator**：部分节点函数可以用 `@observe` 装饰器进一步简化
4. **自定义 Dashboard**：按查询类型、数据源、用户维度做成本和性能看板
5. **集成前端**：前端展示 trace_id 链接，方便调试时一键跳转到 Langfuse UI

---

## 八、相关文件索引

**核心实现**：
- `backend/nl2sql/tracing/__init__.py` — 公开 API
- `backend/nl2sql/tracing/langfuse_client.py` — SDK 单例 + 降级
- `backend/nl2sql/tracing/context.py` — contextvars 管理
- `backend/nl2sql/tracing/tracer.py` — context manager 实现

**集成点**：
- `backend/nl2sql/llm/base.py` — LLM 层模板方法
- `backend/nl2sql/agent/nodes/_step_utils.py` — 节点层 span 创建
- `backend/nl2sql/agent/dispatcher.py` — 分发层 span
- `backend/app/services/chat_service.py` — 服务层 trace 入口

**测试**：
- `backend/tests/test_tracing/test_e2e_tracing.py` — 端到端集成测试
- `backend/tests/test_tracing/` — 全部 tracing 测试（8 个文件）

**部署**：
- `docker-compose.yml` — Langfuse + Postgres 服务
- `Makefile` — langfuse-up/down/logs 命令
- `.env.example` / `backend/.env.example` — 配置示例
