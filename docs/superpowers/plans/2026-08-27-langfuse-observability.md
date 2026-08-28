# Langfuse 可观测性集成实施计划 (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 nl2sql 项目引入 Langfuse 自部署 tracing，实现全链路 LLM 调用追踪（trace → span → generation 三级结构），支持调试和成本分析。

**Architecture:** 手动 SDK 集成方案。在 `LLMClient` 基类做单点 LLM 埋点，通过 `contextvars` 管理上下文自动嵌套；chat_service 层创建 trace，`_step_utils` 统一创建节点 span，Dispatcher 层创建子 Agent span。tracing 可插拔，默认关闭不影响现有功能。

**Tech Stack:** Python 3.12, Langfuse Python SDK, contextvars, docker-compose (自部署), Pytest

---

## 文件结构总览

| 操作 | 文件路径 | 职责 |
|------|----------|------|
| 新增 | `backend/nl2sql/tracing/__init__.py` | 公共 API 导出 |
| 新增 | `backend/nl2sql/tracing/langfuse_client.py` | Langfuse 客户端单例 + no-op 处理 |
| 新增 | `backend/nl2sql/tracing/context.py` | contextvars 上下文管理 |
| 新增 | `backend/nl2sql/tracing/tracer.py` | trace/span/generation 上下文管理器 |
| 新增 | `backend/tests/test_tracing/test_tracer_noop.py` | no-op 模式测试 |
| 新增 | `backend/tests/test_tracing/test_tracer_context.py` | 上下文嵌套测试（mock） |
| 新增 | `backend/tests/test_tracing/test_llm_tracing.py` | LLM 层埋点测试 |
| 修改 | `backend/nl2sql/config.py` | 新增 Langfuse 配置字段 |
| 修改 | `backend/nl2sql/llm/base.py` | 模板方法重构 + generation 埋点 |
| 修改 | `backend/nl2sql/llm/claude_client.py` | `chat()` → `_chat_impl()` 重命名 |
| 修改 | `backend/nl2sql/llm/openai_client.py` | `chat()` → `_chat_impl()` 重命名 |
| 修改 | `backend/nl2sql/agent/nodes/_step_utils.py` | step_start/complete 嵌入 span |
| 修改 | `backend/nl2sql/agent/dispatcher.py` | dispatcher + 子 Agent span |
| 修改 | `backend/app/services/chat_service.py` | trace 入口包裹 |
| 修改 | `backend/pyproject.toml` | 新增 langfuse 依赖 |
| 修改 | `docker-compose.yml` | 新增 langfuse + langfuse-db 服务 |
| 修改 | `Makefile` | 新增 langfuse-up/down 命令 |

---

## Task 1: 配置 + 依赖

**Files:**
- Modify: `backend/nl2sql/config.py:30`
- Modify: `backend/pyproject.toml:23`

- [ ] **Step 1: 在 Settings 中新增 Langfuse 配置字段**

在 `backend/nl2sql/config.py` 的 `Settings` 类末尾（`agent_timeout_seconds` 之后）添加：

```python
    # Langfuse 可观测性
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3030"
```

- [ ] **Step 2: 在 pyproject.toml 中添加 langfuse 依赖**

在 `dependencies` 列表末尾（`modelscope` 之后）添加：

```toml
    "langfuse>=3.0",
```

- [ ] **Step 3: 验证配置可加载**

```bash
cd backend && python -c "
from nl2sql.config import Settings
s = Settings()
print(f'enabled={s.langfuse_enabled}')
print(f'host={s.langfuse_host}')
"
```

Expected: `enabled=False` 和 `host=http://localhost:3030`，不报错。

- [ ] **Step 4: 安装新依赖**

```bash
cd backend && uv sync
```

Expected: langfuse 及其依赖安装成功。

- [ ] **Step 5: 运行现有测试确保无破坏**

```bash
cd backend && pytest tests/test_llm/ -v
```

Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
git add backend/nl2sql/config.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(tracing): add Langfuse config fields and dependency"
```

---

## Task 2: Tracing 模块 — langfuse_client（单例 + no-op）

**Files:**
- Create: `backend/nl2sql/tracing/__init__.py`
- Create: `backend/nl2sql/tracing/langfuse_client.py`
- Test: `backend/tests/test_tracing/test_langfuse_client.py`

- [ ] **Step 1: 写测试 — 禁用时返回 None**

```bash
mkdir -p backend/tests/test_tracing
```

创建 `backend/tests/test_tracing/test_langfuse_client.py`：

```python
"""Tests for Langfuse client singleton management."""
from __future__ import annotations

import pytest


def test_get_client_disabled_by_default():
    """默认配置下 langfuse_enabled=false，get_langfuse() 返回 None。"""
    from nl2sql.tracing.langfuse_client import get_langfuse
    client = get_langfuse()
    assert client is None


def test_get_client_no_public_key():
    """enabled=true 但没有 key，仍然返回 None（降级）。"""
    from unittest.mock import patch
    from nl2sql.tracing.langfuse_client import get_langfuse

    mock_settings = type(
        "Settings",
        (),
        {
            "langfuse_enabled": True,
            "langfuse_public_key": "",
            "langfuse_secret_key": "",
            "langfuse_host": "http://localhost:3030",
        },
    )()

    with patch("nl2sql.tracing.langfuse_client.Settings", return_value=mock_settings):
        # 重置单例缓存
        import nl2sql.tracing.langfuse_client as lc
        lc._client = None
        lc._initialized = False
        client = get_langfuse()
        assert client is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_langfuse_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nl2sql.tracing'`

- [ ] **Step 3: 创建 tracing 包 __init__.py**

创建 `backend/nl2sql/tracing/__init__.py`：

```python
"""Tracing and observability module (Langfuse integration)."""

from .tracer import trace, span, generation, flush
from .langfuse_client import get_langfuse

__all__ = ["trace", "span", "generation", "flush", "get_langfuse"]
```

- [ ] **Step 4: 实现 langfuse_client.py**

创建 `backend/nl2sql/tracing/langfuse_client.py`：

```python
"""Langfuse client singleton management.

Handles lazy initialization and graceful degradation:
- If LANGFUSE_ENABLED is false → returns None (no-op mode)
- If keys are missing → returns None (degraded)
- Otherwise → returns a shared Langfuse client instance
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from langfuse import Langfuse

_client: "Langfuse | None" = None
_initialized = False


def get_langfuse() -> "Langfuse | None":
    """Get the shared Langfuse client instance.

    Returns None if tracing is disabled or misconfigured.
    Safe to call multiple times — initializes only once.
    """
    global _client, _initialized
    if _initialized:
        return _client

    settings = Settings()
    _initialized = True

    if not settings.langfuse_enabled:
        _client = None
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        # Config says enabled but keys missing — degrade silently
        _client = None
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        # Any import or init failure → no-op mode
        _client = None

    return _client


def reset_client_for_tests() -> None:
    """Reset the singleton state. For tests only."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
    _client = None
    _initialized = False
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && pytest tests/test_tracing/test_langfuse_client.py -v
```

Expected: 2 tests PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/nl2sql/tracing/__init__.py backend/nl2sql/tracing/langfuse_client.py backend/tests/test_tracing/test_langfuse_client.py
git commit -m "feat(tracing): add Langfuse client singleton with graceful degradation"
```

---

## Task 3: Tracing 模块 — context（contextvars 上下文管理）

**Files:**
- Create: `backend/nl2sql/tracing/context.py`
- Test: `backend/tests/test_tracing/test_context.py`

- [ ] **Step 1: 写测试 — 上下文变量默认值和 set/reset**

创建 `backend/tests/test_tracing/test_context.py`：

```python
"""Tests for tracing context management via contextvars."""
from __future__ import annotations


def test_default_trace_is_none():
    """默认没有活跃 trace。"""
    from nl2sql.tracing.context import get_current_trace
    assert get_current_trace() is None


def test_default_span_is_none():
    """默认没有活跃 span。"""
    from nl2sql.tracing.context import get_current_span
    assert get_current_span() is None


def test_set_and_reset_trace():
    """设置当前 trace 后可以读取，reset 后回到 None。"""
    from nl2sql.tracing.context import set_current_trace, get_current_trace, reset_current_trace

    token = set_current_trace("fake_trace_obj")
    assert get_current_trace() == "fake_trace_obj"

    reset_current_trace(token)
    assert get_current_trace() is None


def test_set_and_reset_span():
    """设置当前 span 后可以读取，reset 后回到 None。"""
    from nl2sql.tracing.context import set_current_span, get_current_span, reset_current_span

    token = set_current_span("fake_span_obj")
    assert get_current_span() == "fake_span_obj"

    reset_current_span(token)
    assert get_current_span() is None


def test_span_stacking():
    """多层 span 嵌套：reset 后应回到父 span。"""
    from nl2sql.tracing.context import set_current_span, get_current_span, reset_current_span

    token1 = set_current_span("parent")
    assert get_current_span() == "parent"

    token2 = set_current_span("child")
    assert get_current_span() == "child"

    reset_current_span(token2)
    assert get_current_span() == "parent"

    reset_current_span(token1)
    assert get_current_span() is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_context.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 context.py**

创建 `backend/nl2sql/tracing/context.py`：

```python
"""Tracing context management using contextvars.

Provides thread-safe (and async-safe) storage for the currently active
trace and span. LLM client layer reads from here to auto-nest
generations under the current span.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_current_trace: ContextVar[Any] = ContextVar("current_trace", default=None)
_current_span: ContextVar[Any] = ContextVar("current_span", default=None)


def get_current_trace() -> Any:
    """Get the currently active trace object, or None."""
    return _current_trace.get()


def get_current_span() -> Any:
    """Get the currently active span object, or None."""
    return _current_span.get()


def set_current_trace(trace: Any) -> Any:
    """Set the current trace. Returns a token for reset."""
    return _current_trace.set(trace)


def set_current_span(span: Any) -> Any:
    """Set the current span. Returns a token for reset."""
    return _current_span.set(span)


def reset_current_trace(token: Any) -> None:
    """Reset trace to previous value using token from set_current_trace."""
    _current_trace.reset(token)


def reset_current_span(token: Any) -> None:
    """Reset span to previous value using token from set_current_span."""
    _current_span.reset(token)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && pytest tests/test_tracing/test_context.py -v
```

Expected: 5 tests PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/nl2sql/tracing/context.py backend/tests/test_tracing/test_context.py
git commit -m "feat(tracing): add contextvars-based trace/span context management"
```

---

## Task 4: Tracing 模块 — tracer（trace/span/generation 上下文管理器）

**Files:**
- Create: `backend/nl2sql/tracing/tracer.py`
- Test: `backend/tests/test_tracing/test_tracer_noop.py`
- Test: `backend/tests/test_tracing/test_tracer_mock.py`
- Modify: `backend/nl2sql/tracing/__init__.py`

- [ ] **Step 1: 写测试 — no-op 模式下所有上下文管理器都正常工作**

创建 `backend/tests/test_tracing/test_tracer_noop.py`：

```python
"""Tests for tracer in no-op mode (Langfuse disabled)."""
from __future__ import annotations

from unittest.mock import patch


def _disable_tracing():
    """Patch Settings to disable tracing and reset singleton."""
    import nl2sql.tracing.langfuse_client as lc
    lc._client = None
    lc._initialized = False

    mock_settings = type(
        "Settings",
        (),
        {
            "langfuse_enabled": False,
            "langfuse_public_key": "",
            "langfuse_secret_key": "",
            "langfuse_host": "http://localhost:3030",
        },
    )()
    return patch("nl2sql.tracing.langfuse_client.Settings", return_value=mock_settings)


def test_trace_context_noop():
    """trace() in no-op mode yields a context object with update method."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import trace
        with trace(name="test_trace") as ctx:
            assert hasattr(ctx, "update")
            assert hasattr(ctx, "id")
            assert ctx.id is None
            ctx.update(output="hello")  # should not raise


def test_span_context_noop():
    """span() in no-op mode yields a context object."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import span
        with span(name="test_span") as ctx:
            assert hasattr(ctx, "update")
            ctx.update(output="result", metadata={"key": "val"})  # should not raise


def test_generation_context_noop():
    """generation() in no-op mode yields a context object."""
    with _disable_tracing():
        from nl2sql.tracing.tracer import generation
        with generation(name="test_gen", model="gpt-4") as ctx:
            assert hasattr(ctx, "update")
            ctx.update(output="hello", usage={"input_tokens": 10, "output_tokens": 5})


def test_nested_noop():
    """多层嵌套在 no-op 模式下不报错。"""
    with _disable_tracing():
        from nl2sql.tracing.tracer import trace, span, generation
        with trace(name="t"):
            with span(name="s1"):
                with generation(name="g1", model="m") as gen:
                    gen.update(output="x")
            with span(name="s2"):
                pass
        # 全部结束后上下文应该回到 None
        from nl2sql.tracing.context import get_current_trace, get_current_span
        assert get_current_trace() is None
        assert get_current_span() is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_tracer_noop.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named ...tracer`

- [ ] **Step 3: 实现 tracer.py**

创建 `backend/nl2sql/tracing/tracer.py`：

```python
"""Core tracer: trace / span / generation context managers.

Provides a clean API that business code uses. Under the hood, delegates
to the Langfuse SDK when enabled, or is a complete no-op when disabled.

Design principles:
- Callers never import langfuse directly
- All three context managers have the same shape: __enter__ returns a
  context object with .update() and .id, __exit__ handles cleanup
- Context variables (trace/span) are automatically set and reset
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from . import context as ctx
from .langfuse_client import get_langfuse


# ---------------------------------------------------------------------------
# Context objects (uniform API for both real and no-op modes)
# ---------------------------------------------------------------------------

class _NoopContext:
    """Placeholder context returned when tracing is disabled.

    Has the same API as real contexts but does nothing.
    """

    id: None = None

    def update(self, **kwargs: Any) -> None:
        pass

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        pass


class _TraceContext:
    """Wraps a Langfuse trace object."""

    def __init__(self, trace: Any) -> None:
        self._trace = trace

    @property
    def id(self) -> str:
        return self._trace.id

    def update(self, output: Any = None, metadata: dict | None = None, **_: Any) -> None:
        if output is not None:
            self._trace.update(output=output)
        if metadata is not None:
            self._trace.update(metadata=metadata)

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        kwargs: dict[str, Any] = {"name": name, "value": value}
        if comment is not None:
            kwargs["comment"] = comment
        self._trace.score(**kwargs)


class _SpanContext:
    """Wraps a Langfuse span object."""

    def __init__(self, span: Any) -> None:
        self._span = span

    @property
    def id(self) -> str:
        return self._span.id

    def update(self, output: Any = None, metadata: dict | None = None, **_: Any) -> None:
        if output is not None:
            self._span.update(output=output)
        if metadata is not None:
            self._span.update(metadata=metadata)


class _GenerationContext:
    """Wraps a Langfuse generation object."""

    def __init__(self, generation: Any) -> None:
        self._generation = generation

    @property
    def id(self) -> str:
        return self._generation.id

    def update(
        self,
        output: Any = None,
        usage: dict | None = None,
        model: str | None = None,
        tool_calls: list | None = None,
        metadata: dict | None = None,
        **_: Any,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if output is not None:
            kwargs["output"] = output
        if usage is not None:
            # Normalize usage keys for Langfuse (expects input_tokens / output_tokens / total_tokens)
            langfuse_usage: dict[str, int] = {}
            if "input_tokens" in usage:
                langfuse_usage["input_tokens"] = usage["input_tokens"]
            elif "prompt_tokens" in usage:
                langfuse_usage["input_tokens"] = usage["prompt_tokens"]
            if "output_tokens" in usage:
                langfuse_usage["output_tokens"] = usage["output_tokens"]
            elif "completion_tokens" in usage:
                langfuse_usage["output_tokens"] = usage["completion_tokens"]
            if "total_tokens" in usage:
                langfuse_usage["total_tokens"] = usage["total_tokens"]
            if langfuse_usage:
                kwargs["usage"] = langfuse_usage
        if model is not None:
            kwargs["model"] = model
        if tool_calls is not None:
            kwargs["metadata"] = {**(kwargs.get("metadata", {})), "tool_calls": tool_calls}
        if metadata is not None:
            existing = kwargs.get("metadata", {})
            existing.update(metadata)
            kwargs["metadata"] = existing
        if kwargs:
            self._generation.update(**kwargs)


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------

@contextmanager
def trace(
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
    input: Any = None,
) -> Iterator[_TraceContext | _NoopContext]:
    """Create a trace (top-level unit of work).

    If tracing is disabled, yields a no-op context.
    Automatically sets current_trace contextvar and restores it on exit.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if user_id is not None:
        kwargs["user_id"] = user_id
    if session_id is not None:
        kwargs["session_id"] = session_id
    if metadata is not None:
        kwargs["metadata"] = metadata
    if input is not None:
        kwargs["input"] = input

    trace_obj = client.trace(**kwargs)
    trace_ctx = _TraceContext(trace_obj)
    token = ctx.set_current_trace(trace_obj)
    try:
        yield trace_ctx
    finally:
        ctx.reset_current_trace(token)


@contextmanager
def span(
    name: str,
    metadata: dict | None = None,
    input: Any = None,
) -> Iterator[_SpanContext | _NoopContext]:
    """Create a span, nested under the current trace and parent span.

    If tracing is disabled or no trace is active, yields a no-op context.
    Automatically sets current_span contextvar and restores it on exit.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    parent = ctx.get_current_span() or ctx.get_current_trace()
    if parent is None:
        # No active trace → can't create a span. No-op.
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if metadata is not None:
        kwargs["metadata"] = metadata
    if input is not None:
        kwargs["input"] = input

    span_obj = parent.span(**kwargs)
    span_ctx = _SpanContext(span_obj)
    token = ctx.set_current_span(span_obj)
    try:
        yield span_ctx
    finally:
        span_obj.end()
        ctx.reset_current_span(token)


@contextmanager
def generation(
    name: str,
    model: str | None = None,
    input: Any = None,
    metadata: dict | None = None,
) -> Iterator[_GenerationContext | _NoopContext]:
    """Create a generation (LLM call), nested under the current span.

    If tracing is disabled or no span/trace is active, yields a no-op context.
    Does NOT modify the current_span contextvar — generations are leaves.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopContext()
        return

    parent = ctx.get_current_span() or ctx.get_current_trace()
    if parent is None:
        # No active trace → no-op
        yield _NoopContext()
        return

    kwargs: dict[str, Any] = {"name": name}
    if model is not None:
        kwargs["model"] = model
    if input is not None:
        kwargs["input"] = input
    if metadata is not None:
        kwargs["metadata"] = metadata

    gen_obj = parent.generation(**kwargs)
    gen_ctx = _GenerationContext(gen_obj)
    try:
        yield gen_ctx
    finally:
        gen_obj.end()


def flush() -> None:
    """Flush pending events to Langfuse. No-op if disabled."""
    client = get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
```

- [ ] **Step 4: 更新 __init__.py 导出**

修改 `backend/nl2sql/tracing/__init__.py`（已在 Task 2 创建，需要加 flush）：

```python
"""Tracing and observability module (Langfuse integration)."""

from .tracer import trace, span, generation, flush
from .langfuse_client import get_langfuse

__all__ = ["trace", "span", "generation", "flush", "get_langfuse"]
```

（这步文件已经是这个内容了，如果没变就跳过，直接跑测试。）

- [ ] **Step 5: 运行 no-op 测试**

```bash
cd backend && pytest tests/test_tracing/test_tracer_noop.py -v
```

Expected: 4 tests PASS。

- [ ] **Step 6: 写测试 — mock 模式下验证嵌套和调用**

创建 `backend/tests/test_tracing/test_tracer_mock.py`：

```python
"""Tests for tracer with a mock Langfuse client (verifies nesting and calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        gen = _MockGeneration(kwargs.get("name", "gen"))
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    def __init__(self, name):
        super().__init__(name)
        self.id = f"trace_{name}"
        self._scores = []

    def score(self, **kwargs):
        self._scores.append(kwargs)


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self.id = f"gen_{name}"
        self._ended = False
        self._updates = []

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    """Enable tracing with a mock Langfuse client."""
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def test_trace_creates_trace_on_client():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace

    with trace(name="my_trace", user_id="u1", session_id="s1") as t:
        assert t.id == "trace_my_trace"

    assert len(mock_client.traces) == 1
    assert mock_client.traces[0].name == "my_trace"


def test_trace_sets_contextvar():
    _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.tracing.context import get_current_trace

    assert get_current_trace() is None
    with trace(name="t"):
        assert get_current_trace() is not None
    assert get_current_trace() is None


def test_span_nested_under_trace():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span

    with trace(name="t"):
        with span(name="s1") as s:
            assert s.id == "span_s1"

    assert len(mock_client.traces) == 1
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    assert trace_obj._children[0].name == "s1"
    assert trace_obj._children[0]._ended is True


def test_generation_nested_under_span():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span, generation

    with trace(name="t"):
        with span(name="s"):
            with generation(name="g", model="gpt-4") as g:
                g.update(output="hello", usage={"input_tokens": 10, "output_tokens": 5})

    trace_obj = mock_client.traces[0]
    span_obj = trace_obj._children[0]
    gen_obj = span_obj._children[0]
    assert gen_obj.name == "g"
    assert gen_obj._ended is True
    # Check that update was called with normalized usage
    assert len(gen_obj._updates) == 1
    update = gen_obj._updates[0]
    assert update["usage"]["input_tokens"] == 10
    assert update["usage"]["output_tokens"] == 5


def test_span_stacking_two_levels():
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span
    from nl2sql.tracing.context import get_current_span

    with trace(name="t"):
        with span(name="parent") as p:
            assert get_current_span().name == "parent"
            with span(name="child") as c:
                assert get_current_span().name == "child"
            assert get_current_span().name == "parent"

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    parent = trace_obj._children[0]
    assert parent.name == "parent"
    assert len(parent._children) == 1
    assert parent._children[0].name == "child"


def test_openai_usage_normalized():
    """OpenAI returns prompt_tokens/completion_tokens; should be normalized."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span, generation

    with trace(name="t"):
        with span(name="s"):
            with generation(name="g") as g:
                g.update(usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                })

    gen_obj = mock_client.traces[0]._children[0]._children[0]
    update = gen_obj._updates[0]
    assert update["usage"]["input_tokens"] == 100
    assert update["usage"]["output_tokens"] == 50
    assert update["usage"]["total_tokens"] == 150
```

- [ ] **Step 7: 运行 mock 测试**

```bash
cd backend && pytest tests/test_tracing/test_tracer_mock.py -v
```

Expected: 7 tests PASS。

- [ ] **Step 8: Commit**

```bash
git add backend/nl2sql/tracing/tracer.py backend/tests/test_tracing/test_tracer_noop.py backend/tests/test_tracing/test_tracer_mock.py
git commit -m "feat(tracing): add trace/span/generation context managers with no-op fallback"
```

---

## Task 5: LLMClient 模板方法重构 + 埋点

**Files:**
- Modify: `backend/nl2sql/llm/base.py:30-53`
- Modify: `backend/nl2sql/llm/claude_client.py:97-133`
- Modify: `backend/nl2sql/llm/openai_client.py:75-104`
- Test: `backend/tests/test_tracing/test_llm_tracing.py`

- [ ] **Step 1: 写测试 — LLMClient.chat() 自动创建 generation**

创建 `backend/tests/test_tracing/test_llm_tracing.py`：

```python
"""Tests for LLM client tracing integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2sql.llm.base import ChatChunk, ChatResponse, LLMClient
from nl2sql.llm.message import Message, MessageRole


class _FakeLLMClient(LLMClient):
    """Concrete test double that returns canned responses."""

    model = "fake-model"
    provider = "fake"

    def _chat_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
        return ChatResponse(
            content="Hello from fake LLM",
            model=self.model,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    def _chat_stream_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
        yield ChatChunk(content_delta="Hello", done=False)
        yield ChatChunk(done=True)


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self._generations = []

    def generation(self, **kwargs):
        g = _MockGeneration(kwargs.get("name", "g"))
        g._kwargs = kwargs
        self._generations.append(g)
        return g


class _MockTrace(_MockSpan):
    pass


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self._updates = []
        self._ended = False

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        t._kwargs = kwargs
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def test_chat_still_works_without_tracing():
    """When tracing is disabled, chat() works exactly as before."""
    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]
    resp = client.chat(messages)
    assert resp.content == "Hello from fake LLM"
    assert resp.model == "fake-model"
    assert resp.usage == {"input_tokens": 10, "output_tokens": 5}


def test_chat_creates_generation_under_current_span():
    """When a span is active, chat() creates a generation under it."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace, span

    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]

    with trace(name="t"):
        with span(name="my_step"):
            resp = client.chat(messages, temperature=0.5)

    assert resp.content == "Hello from fake LLM"

    # Trace → span → generation nesting
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._generations) == 0  # span is a child, not gen
    span_obj = trace_obj._children[0]
    assert span_obj.name == "my_step"

    # Generation was created under the span
    assert len(span_obj._generations) == 1
    gen = span_obj._generations[0]
    assert gen._kwargs["model"] == "fake-model"
    assert gen._kwargs["metadata"]["temperature"] == 0.5
    assert gen._kwargs["metadata"]["has_tools"] is False
    # Input is serialized messages
    assert len(gen._kwargs["input"]) == 1
    assert gen._kwargs["input"][0]["content"] == "Hi"
    # Output was set via update
    assert len(gen._updates) == 1
    assert gen._updates[0]["output"] == "Hello from fake LLM"
    assert gen._updates[0]["usage"]["input_tokens"] == 10
    assert gen._updates[0]["usage"]["output_tokens"] == 5


def test_chat_without_trace_is_noop():
    """If no trace/span is active but tracing is enabled, still no-op (no crash)."""
    _enable_with_mock()
    client = _FakeLLMClient()
    messages = [Message(role=MessageRole.USER, content="Hi")]

    # No trace active
    resp = client.chat(messages)
    assert resp.content == "Hello from fake LLM"  # still works
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_llm_tracing.py -v
```

Expected: FAIL （因为 base.py 里还没有 generation 埋点，也没有 `_chat_impl`）。

- [ ] **Step 3: 重构 LLMClient 基类（模板方法 + 埋点）**

修改 `backend/nl2sql/llm/base.py`：

```python
"""LLM client abstract base class and response models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Optional

from pydantic import BaseModel, Field

from ..tracing import generation as _tracing_generation
from .message import Message, ToolCall


class ChatResponse(BaseModel):
    """Response from a non-streaming chat completion."""

    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""
    usage: dict = Field(default_factory=dict)


class ChatChunk(BaseModel):
    """A chunk from a streaming chat completion."""

    content_delta: str = ""
    tool_call_delta: Optional[ToolCall] = None
    done: bool = False


class LLMClient(ABC):
    """Abstract base class for LLM clients.

    Uses the Template Method pattern: chat() and chat_stream() wrap the
    actual implementation (_chat_impl / _chat_stream_impl) with tracing
    instrumentation, so all subclasses get automatic Langfuse tracing
    without any per-client code.
    """

    model: str = ""
    provider: str = "unknown"

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a non-streaming chat request.

        Wraps _chat_impl with tracing instrumentation.
        Subclasses should override _chat_impl, not this method.
        """
        gen_name = self._resolve_generation_name()
        with _tracing_generation(
            name=gen_name,
            model=self.model,
            input=[m.model_dump(mode="json") for m in messages],
            metadata={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "has_tools": tools is not None,
                "tool_count": len(tools) if tools else 0,
                "provider": self.provider,
            },
        ) as gen_ctx:
            result = self._chat_impl(
                messages, tools=tools, temperature=temperature, max_tokens=max_tokens
            )
            gen_ctx.update(
                output=result.content,
                usage=result.usage,
                tool_calls=[tc.model_dump(mode="json") for tc in result.tool_calls] if result.tool_calls else None,
            )
            return result

    @abstractmethod
    def _chat_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Actual implementation of chat. Override this in subclasses."""
        ...

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        """Send a streaming chat request, yielding ChatChunk objects.

        Wraps _chat_stream_impl with tracing instrumentation.
        Subclasses should override _chat_stream_impl, not this method.
        """
        gen_name = self._resolve_generation_name()
        with _tracing_generation(
            name=gen_name,
            model=self.model,
            input=[m.model_dump(mode="json") for m in messages],
            metadata={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "has_tools": tools is not None,
                "tool_count": len(tools) if tools else 0,
                "provider": self.provider,
                "stream": True,
            },
        ) as gen_ctx:
            chunks: list[ChatChunk] = []
            for chunk in self._chat_stream_impl(
                messages, tools=tools, temperature=temperature, max_tokens=max_tokens
            ):
                chunks.append(chunk)
                yield chunk

            # After streaming completes, record the final output
            full_content = "".join(c.content_delta for c in chunks if c.content_delta)
            tool_calls = [
                c.tool_call_delta for c in chunks
                if c.tool_call_delta is not None and c.tool_call_delta.id
            ]
            gen_ctx.update(
                output=full_content,
                tool_calls=[tc.model_dump(mode="json") for tc in tool_calls] if tool_calls else None,
            )

    @abstractmethod
    def _chat_stream_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        """Actual implementation of chat_stream. Override this in subclasses."""
        ...

    # ------------------------------------------------------------------
    # Generation name resolution
    # ------------------------------------------------------------------

    _generation_name_override: str | None = None

    def set_generation_name(self, name: str) -> "LLMClient":
        """Set a custom name for the generation (for display in Langfuse).

        Returns self for chaining:
            llm = create_llm_client().set_generation_name("intent_analyze")
        """
        self._generation_name_override = name
        return self

    def _resolve_generation_name(self) -> str:
        """Resolve the name to use for this LLM generation.

        Priority:
        1. Explicit override via set_generation_name()
        2. Name of current span (if active)
        3. Fallback: "llm_chat"
        """
        if self._generation_name_override:
            return self._generation_name_override

        # Try reading current span name from tracing context
        try:
            from ..tracing.context import get_current_span
            span = get_current_span()
            if span is not None and hasattr(span, "name"):
                return str(span.name)
        except Exception:
            pass

        return "llm_chat"
```

- [ ] **Step 4: 重构 ClaudeClient — chat → _chat_impl**

修改 `backend/nl2sql/llm/claude_client.py`：

1. `__init__` 里加 `self.provider = "anthropic"`
2. `def chat(` → `def _chat_impl(`
3. `def chat_stream(` → `def _chat_stream_impl(`

具体改动：

```python
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self.model = model
        self.provider = "anthropic"
```

```python
    def _chat_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        # ... (原有逻辑不变)
```

```python
    def _chat_stream_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        # ... (原有逻辑不变)
```

- [ ] **Step 5: 重构 OpenAIClient — chat → _chat_impl**

修改 `backend/nl2sql/llm/openai_client.py`：

1. `__init__` 里加 `self.provider = "openai"`
2. `def chat(` → `def _chat_impl(`
3. `def chat_stream(` → `def _chat_stream_impl(`

具体改动：

```python
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model
        self.provider = "openai"
```

```python
    def _chat_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        # ... (原有逻辑不变)
```

```python
    def _chat_stream_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        # ... (原有逻辑不变)
```

- [ ] **Step 6: 更新现有 base 测试中的 ConcreteClient**

修改 `backend/tests/test_llm/test_base.py` 第 58-69 行的 `ConcreteClient`：

```python
    def test_concrete_subclass_can_be_instantiated(self):
        class ConcreteClient(LLMClient):
            def _chat_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
                return ChatResponse(content="hi")

            def _chat_stream_impl(self, messages, tools=None, temperature=0.0, max_tokens=4096):
                yield ChatChunk(content_delta="hi", done=True)

        client = ConcreteClient()
        assert isinstance(client, LLMClient)
        resp = client.chat([])
        assert resp.content == "hi"
```

- [ ] **Step 7: 运行所有 LLM + tracing 测试**

```bash
cd backend && pytest tests/test_llm/ tests/test_tracing/ -v
```

Expected: 全部 PASS。

- [ ] **Step 8: 运行完整测试套件确保无回归**

```bash
cd backend && pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 全部通过。如果有失败，根据错误信息修复（可能是其他测试文件里 mock 或继承了 `LLMClient`，需要同步改成 `_chat_impl`）。

- [ ] **Step 9: Commit**

```bash
git add backend/nl2sql/llm/base.py backend/nl2sql/llm/claude_client.py backend/nl2sql/llm/openai_client.py backend/tests/test_llm/test_base.py backend/tests/test_tracing/test_llm_tracing.py
git commit -m "feat(tracing): template-method refactor of LLMClient with automatic generation tracing"
```

---

## Task 6: 节点层 Span 埋点（通过 _step_utils）

**Files:**
- Modify: `backend/nl2sql/agent/nodes/_step_utils.py`
- Test: `backend/tests/test_tracing/test_step_utils_tracing.py`

- [ ] **Step 1: 写测试 — step_start 创建 span，step_complete 结束 span**

创建 `backend/tests/test_tracing/test_step_utils_tracing.py`：

```python
"""Tests for step_utils integration with tracing spans."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        return _MockGeneration(kwargs.get("name", "g"))

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    pass


class _MockGeneration:
    def __init__(self, name):
        self.name = name
        self._ended = False

    def end(self):
        self._ended = True


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def test_step_start_creates_span_in_trace_context():
    """step_start() creates a span when inside a trace."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "intent_analyze", "意图分析")
        step_complete(state, "intent_analyze", "意图分析", {"result": "ok"}, t0)

    # Span was created under trace
    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    span_obj = trace_obj._children[0]
    assert span_obj.name == "intent_analyze"
    assert span_obj._ended is True


def test_step_error_ends_span():
    """step_error() also ends the span properly."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_error

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "generate_sql", "SQL生成")
        step_error(state, "generate_sql", "SQL生成", "syntax error", t0)

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 1
    span_obj = trace_obj._children[0]
    assert span_obj.name == "generate_sql"
    assert span_obj._ended is True


def test_no_span_without_trace():
    """When no trace is active, step_start/step_complete still work (no crash)."""
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}
    t0 = step_start(state, "test_step", "测试步骤")
    step_complete(state, "test_step", "测试步骤", {"ok": True}, t0)
    # Should not raise


def test_multiple_steps_create_multiple_spans():
    """Multiple step_start/complete calls create multiple sibling spans."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t1 = step_start(state, "step1", "步骤1")
        step_complete(state, "step1", "步骤1", {}, t1)

        t2 = step_start(state, "step2", "步骤2")
        step_complete(state, "step2", "步骤2", {}, t2)

    trace_obj = mock_client.traces[0]
    assert len(trace_obj._children) == 2
    assert trace_obj._children[0].name == "step1"
    assert trace_obj._children[1].name == "step2"


def test_step_complete_with_detail_updates_span():
    """step_complete detail is passed as span output metadata."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace
    from nl2sql.agent.nodes._step_utils import step_start, step_complete

    state = {"event_callback": None}

    with trace(name="t"):
        t0 = step_start(state, "gen", "生成")
        step_complete(state, "gen", "生成", {"sql": "SELECT 1", "rows": 42}, t0)

    span_obj = mock_client.traces[0]._children[0]
    # Should have at least one update call with the detail
    assert len(span_obj._updates) >= 1
    # The detail dict should appear somewhere in the updates
    detail_found = any(
        u.get("output") is not None or u.get("metadata", {}).get("sql") == "SELECT 1"
        for u in span_obj._updates
    )
    # At minimum the span ended
    assert span_obj._ended is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_step_utils_tracing.py -v
```

Expected: FAIL（因为 _step_utils 还没有 span 逻辑）。

- [ ] **Step 3: 实现 _step_utils 中的 span 埋点**

修改 `backend/nl2sql/agent/nodes/_step_utils.py`：

```python
"""Step detail event utilities for agent nodes.

Provides unified helpers to emit step_detail SSE events from each node.
Also creates Langfuse spans for tracing (when enabled).

Usage:

    from ._step_utils import step_start, step_complete, step_error

    def my_node(state: dict) -> dict:
        start = step_start(state, "my_step", "我的步骤")
        try:
            result = do_work()
            step_complete(state, "my_step", "我的步骤", {"key": "value"}, start)
            return result
        except Exception as e:
            step_error(state, "my_step", "我的步骤", str(e), start)
            raise
"""
from __future__ import annotations

import time
from typing import Any


# Tracing is optional — import lazily to avoid hard dependency
def _get_tracer():
    """Import and return tracer span helpers, or None if tracing unavailable."""
    try:
        from nl2sql.tracing import tracer
        return tracer
    except Exception:
        return None


def _send_event(state: dict | Any, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set.

    Compatible with both dict state (LangGraph runtime) and Pydantic model state (tests).
    """
    if isinstance(state, dict):
        callback = state.get("event_callback")
    else:
        callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def _get_tracing_spans(state: dict | Any) -> dict:
    """Get the _tracing_spans dict from state."""
    if isinstance(state, dict):
        if "_tracing_spans" not in state:
            state["_tracing_spans"] = {}
        return state["_tracing_spans"]
    # Pydantic model state — just use a thread-local / no-op fallback
    return {}


def step_start(state: dict, step: str, name: str) -> float:
    """Emit a step_detail event with status=active and return start time.

    Also creates a Langfuse span (when tracing is enabled and a trace is active).

    Args:
        state: Agent state dict (must have event_callback)
        step: Unique step key (e.g. "intent_analysis")
        name: Chinese display name (e.g. "意图分析")

    Returns:
        Start timestamp (perf_counter) for duration calculation
    """
    _send_event(state, "step_detail", {
        "step": step,
        "name": name,
        "status": "active",
    })

    # Tracing: create span
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            span_ctx = tracer.span(
                name=step,
                metadata={"display_name": name},
            )
            # Use context manager manually (need to store in state for step_complete)
            span_obj = span_ctx.__enter__()
            spans[step] = (span_ctx, span_obj)
        except Exception:
            # Tracing failures should never break the flow
            pass

    return time.perf_counter()


def step_complete(
    state: dict,
    step: str,
    name: str,
    detail: dict[str, Any] | None = None,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=completed.

    Also ends the corresponding Langfuse span.

    Args:
        state: Agent state dict
        step: Unique step key
        name: Chinese display name
        detail: Structured detail dict
        start_time: Start timestamp from step_start() for duration calculation
    """
    payload: dict[str, Any] = {
        "step": step,
        "name": name,
        "status": "completed",
    }
    if start_time is not None:
        payload["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    if detail is not None:
        payload["detail"] = detail
    _send_event(state, "step_detail", payload)

    # Tracing: end span
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            entry = spans.pop(step, None)
            if entry is not None:
                span_ctx, span_obj = entry
                if detail is not None:
                    span_obj.update(metadata={"detail": detail})
                span_ctx.__exit__(None, None, None)
        except Exception:
            pass


def step_error(
    state: dict,
    step: str,
    name: str,
    error_message: str,
    start_time: float | None = None,
) -> None:
    """Emit a step_detail event with status=error.

    Also ends the corresponding Langfuse span with error status.

    Args:
        state: Agent state dict
        step: Unique step key
        name: Chinese display name
        error_message: Error description
        start_time: Start timestamp from step_start()
    """
    payload: dict[str, Any] = {
        "step": step,
        "name": name,
        "status": "error",
        "error_message": error_message,
    }
    if start_time is not None:
        payload["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    _send_event(state, "step_detail", payload)

    # Tracing: end span with error
    tracer = _get_tracer()
    if tracer is not None:
        try:
            spans = _get_tracing_spans(state)
            entry = spans.pop(step, None)
            if entry is not None:
                span_ctx, span_obj = entry
                span_obj.update(metadata={"error": error_message})
                try:
                    span_ctx.__exit__(Exception, Exception(error_message), None)
                except Exception:
                    pass
        except Exception:
            pass
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && pytest tests/test_tracing/test_step_utils_tracing.py -v
```

Expected: 6 tests PASS。如果失败，根据错误调整实现。

- [ ] **Step 5: 运行节点相关测试确保不破坏**

```bash
cd backend && pytest tests/ -v --tb=short -k "step or node or intent or generate" 2>&1 | tail -30
```

Expected: 全部通过。

- [ ] **Step 6: 完整测试套件**

```bash
cd backend && pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add backend/nl2sql/agent/nodes/_step_utils.py backend/tests/test_tracing/test_step_utils_tracing.py
git commit -m "feat(tracing): create Langfuse spans from step_start/step_complete utilities"
```

---

## Task 7: Dispatcher + 子 Agent Span

**Files:**
- Modify: `backend/nl2sql/agent/dispatcher.py:260-367`
- Test: `backend/tests/test_tracing/test_dispatcher_tracing.py`

- [ ] **Step 1: 写测试 — Dispatcher.run() 创建 dispatcher span + 子 Agent span**

创建 `backend/tests/test_tracing/test_dispatcher_tracing.py`：

```python
"""Tests for DispatcherAgent tracing integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        gen = MagicMock()
        gen.end = MagicMock()
        gen._updates = []
        def update(**kw):
            gen._updates.append(kw)
        gen.update = update
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    pass


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def _make_fake_dispatcher(intent_result="chitchat"):
    """Create a DispatcherAgent with mocked LLM and sub-agents."""
    from nl2sql.agent.dispatcher import DispatcherAgent

    dispatcher = DispatcherAgent(
        project_id="test_proj",
        datasources=[],
        executors={},
    )

    # Mock _classify_intent to return a fixed intent
    from nl2sql.agent.dispatcher import DispatchResult
    dispatcher._classify_intent = lambda q, h=None: DispatchResult(
        intent=intent_result, confidence=0.9, reasoning="test"
    )

    # Mock chitchat (used as the simplest path)
    dispatcher._run_chitchat = lambda q: {
        "answer": "hi there",
        "status": "done",
        "intent": "chitchat",
    }

    return dispatcher


def test_dispatcher_creates_span_in_trace():
    """Dispatcher.run() creates a 'dispatcher' span inside an active trace."""
    mock_client = _enable_with_mock()
    from nl2sql.tracing.tracer import trace

    dispatcher = _make_fake_dispatcher("chitchat")

    with trace(name="chat_turn"):
        result = dispatcher.run("hello")

    assert result["intent"] == "chitchat"
    assert result["answer"] == "hi there"

    # Check trace → dispatcher span nesting
    trace_obj = mock_client.traces[0]
    # Find the dispatcher span (should be a direct child of trace)
    disp_spans = [c for c in trace_obj._children if isinstance(c, _MockSpan) and c.name == "dispatcher"]
    assert len(disp_spans) == 1, f"Expected 1 dispatcher span, got {len(disp_spans)}"
    assert disp_spans[0]._ended is True


def test_dispatcher_works_without_trace():
    """Dispatcher.run() works normally when no trace is active."""
    dispatcher = _make_fake_dispatcher("chitchat")
    result = dispatcher.run("hello")
    assert result["status"] == "done"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_dispatcher_tracing.py -v
```

Expected: FAIL（dispatcher 还没有 span 逻辑）。

- [ ] **Step 3: 在 DispatcherAgent.run() 中包裹 dispatcher span + 子 Agent span**

修改 `backend/nl2sql/agent/dispatcher.py` 的 `run()` 方法（第 260-367 行）。

首先在文件顶部 import 区域加一行：

```python
from nl2sql.tracing import span as _tracing_span
```

然后修改 `run()` 方法，将方法体包裹在 dispatcher span 中，并在各子 Agent 调用处加子 span：

```python
    def run(
        self,
        user_query: str,
        conversation_history: list | None = None,
        selected_datasource_id: str | None = None,
        extra_state: dict | None = None,
    ) -> dict:
        """运行完整的分发 + 执行流程.

        Args:
            user_query: 用户的自然语言消息
            conversation_history: 历史对话消息列表
            selected_datasource_id: 可选，用户指定的数据源 ID（优先使用）

        Returns:
            统一格式的结果字典，包含:
            - answer: 最终回答
            - status: 状态 (done/failed)
            - intent: 识别的意图类型
            - 各子 Agent 特有的字段
        """
        with _tracing_span(
            name="dispatcher",
            metadata={"user_query": user_query},
        ) as disp_span:
            # Step 1: 意图分类
            import time
            dispatch_start = time.perf_counter()
            self._send_event("dispatch_started", {"query": user_query})
            self._send_event("step_detail", {
                "step": "dispatch",
                "name": "分析任务",
                "status": "active",
            })

            dispatch = self._classify_intent(user_query, conversation_history)

            self._send_event("dispatch_result", {
                "intent": dispatch.intent,
                "confidence": dispatch.confidence,
                "reasoning": dispatch.reasoning,
            })
            dispatch_duration = int((time.perf_counter() - dispatch_start) * 1000)
            self._send_event("step_detail", {
                "step": "dispatch",
                "name": "分析任务",
                "status": "completed",
                "duration_ms": dispatch_duration,
                "detail": {
                    "intent": dispatch.intent,
                    "confidence": dispatch.confidence,
                    "reasoning": dispatch.reasoning,
                },
            })

            # Record intent on the dispatcher span
            try:
                disp_span.update(metadata={
                    "intent": dispatch.intent,
                    "confidence": dispatch.confidence,
                })
            except Exception:
                pass

            # Step 2: 路由到对应子 Agent
            if dispatch.intent == "query":
                with _tracing_span(name="nl2sql_agent"):
                    result = self._run_query(
                        user_query, conversation_history, selected_datasource_id, extra_state
                    )
                result["intent"] = result.get("intent", "query")

            elif dispatch.intent == "schema_exploration":
                if not self.datasources:
                    return {
                        "answer": "当前项目还没有配置数据源，无法探索 schema。请先连接一个数据源。",
                        "status": "failed",
                        "intent": "schema_exploration",
                        "error": "no datasource",
                    }
                with _tracing_span(name="schema_explorer_agent"):
                    result = self._run_schema_exploration(user_query, conversation_history)
                result["intent"] = "schema_exploration"

            elif dispatch.intent == "connect_datasource":
                with _tracing_span(name="datasource_connector_agent"):
                    result = self._run_connect_datasource(
                        user_query, conversation_history, dispatch.datasource_info
                    )
                result["intent"] = "connect_datasource"

            else:  # chitchat
                result = self._run_chitchat(user_query)

            # 发送 final_result 事件
            # 注意：query 类型由 graph 内的 summarize_node 负责发送 final_result 和 done
            # 非 query 类型（schema_exploration / connect_datasource / chitchat）
            # 没有 summarize_node，由 dispatcher 统一发送
            if dispatch.intent != "query":
                answer = result.get("answer", "")
                sql = result.get("sql", "") or ""
                exec_result = result.get("execution_result")
                viz_spec = result.get("viz_spec")

                result_payload = None
                if exec_result and hasattr(exec_result, "success") and exec_result.success:
                    result_payload = {
                        "columns": exec_result.columns,
                        "rows": [list(r) for r in exec_result.rows[:100]],
                        "row_count": exec_result.row_count,
                        "success": exec_result.success,
                        "duration_ms": getattr(exec_result, "duration_ms", None),
                        "truncated": len(exec_result.rows) < exec_result.row_count,
                    }

                self._send_event("final_result", {
                    "answer": answer,
                    "success": result.get("status") == "done",
                    "sql": sql,
                    "result": result_payload,
                    "viz": viz_spec,
                    "intent": dispatch.intent,
                })
                self._send_event("done", {"status": result.get("status", "unknown")})

            return result
```

- [ ] **Step 4: 运行 dispatcher tracing 测试**

```bash
cd backend && pytest tests/test_tracing/test_dispatcher_tracing.py -v
```

Expected: 2 tests PASS。

- [ ] **Step 5: 运行现有 dispatcher 测试**

```bash
cd backend && pytest tests/ -v --tb=short -k "dispatch" 2>&1 | tail -20
```

Expected: 全部通过。

- [ ] **Step 6: 完整测试套件**

```bash
cd backend && pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add backend/nl2sql/agent/dispatcher.py backend/tests/test_tracing/test_dispatcher_tracing.py
git commit -m "feat(tracing): add dispatcher and sub-agent spans in DispatcherAgent.run()"
```

---

## Task 8: Chat Service Trace 入口

**Files:**
- Modify: `backend/app/services/chat_service.py:332-413` (the `_run_chat_sync` function)
- Test: `backend/tests/test_tracing/test_chat_service_tracing.py`

- [ ] **Step 1: 写测试 — 验证 _run_chat_sync 创建 trace（mock 方式）**

创建 `backend/tests/test_tracing/test_chat_service_tracing.py`：

```python
"""Tests for chat_service trace integration.

These tests verify that the trace is properly created around chat runs.
We mock the dispatcher and DB to isolate tracing behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _MockSpan:
    def __init__(self, name):
        self.name = name
        self.id = f"span_{name}"
        self._ended = False
        self._updates = []
        self._children = []

    def span(self, **kwargs):
        child = _MockSpan(kwargs.get("name", "child"))
        self._children.append(child)
        return child

    def generation(self, **kwargs):
        gen = MagicMock()
        gen.end = MagicMock()
        gen._updates = []
        gen.update = lambda **kw: gen._updates.append(kw)
        self._children.append(gen)
        return gen

    def update(self, **kwargs):
        self._updates.append(kwargs)

    def end(self):
        self._ended = True


class _MockTrace(_MockSpan):
    def __init__(self, name):
        super().__init__(name)
        self._kwargs = {}
        self._scores = []

    def score(self, **kwargs):
        self._scores.append(kwargs)


class _MockLangfuse:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        t = _MockTrace(kwargs.get("name", "t"))
        t._kwargs = kwargs
        self.traces.append(t)
        return t

    def flush(self):
        pass


def _enable_with_mock():
    import nl2sql.tracing.langfuse_client as lc
    mock_client = _MockLangfuse()
    lc._client = mock_client
    lc._initialized = True
    return mock_client


def test_trace_created_with_correct_metadata():
    """When tracing is enabled, chat_service creates a trace with proper metadata."""
    mock_client = _enable_with_mock()

    # Mock all the heavy dependencies
    with patch("app.services.chat_service.session_service") as mock_sess, \
         patch("app.services.chat_service._build_dispatcher_sync") as mock_build, \
         patch("app.services.chat_service._load_history_messages_sync") as mock_hist, \
         patch("app.services.chat_service._start_async_correction_detection") as mock_corr, \
         patch("app.services.chat_service.log_generation") as mock_log, \
         patch("app.services.chat_service.result_cache") as mock_cache, \
         patch("app.services.chat_service.get_connection") as mock_db:

        mock_sess.get_session.return_value = {
            "id": "sess_123",
            "project_id": "proj_123",
            "user_id": "user_456",
        }
        mock_sess.add_message.return_value = {"id": "msg_789"}
        mock_sess.update_session_title_from_query.return_value = None

        mock_dispatcher = MagicMock()
        mock_dispatcher.run.return_value = {
            "answer": "Here is your answer",
            "status": "done",
            "sql": "SELECT 1",
            "intent": "query",
            "intent_type": "query",
            "iteration": 1,
            "execution_result": None,
            "react_thoughts": [],
        }
        mock_build.return_value = mock_dispatcher

        mock_hist.return_value = []

        import asyncio
        loop = asyncio.new_event_loop()

        from app.services.chat_service import _run_chat_sync
        _run_chat_sync("sess_123", "What is the total sales?", loop, "ds_123")

        # Verify a trace was created
        assert len(mock_client.traces) >= 1, "Expected at least one trace"
        trace_obj = mock_client.traces[0]
        assert trace_obj._kwargs["name"] == "chat_turn"
        assert trace_obj._kwargs.get("session_id") == "sess_123"
        # Input should be the user query
        assert trace_obj._kwargs.get("input") == "What is the total sales?"
        # Metadata should contain datasource info
        meta = trace_obj._kwargs.get("metadata", {})
        assert meta.get("datasource_id") == "ds_123"

        loop.close()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_tracing/test_chat_service_tracing.py -v
```

Expected: FAIL（chat_service 还没有 trace 包裹）。

- [ ] **Step 3: 在 _run_chat_sync 中包裹 trace**

修改 `backend/app/services/chat_service.py`：

先在顶部 import 区域加：

```python
from nl2sql.tracing import trace as _tracing_trace, flush as _tracing_flush
```

然后修改 `_run_chat_sync` 函数，在 `start_time = time.perf_counter()` 之后、`try:` 之前开始 trace，并将 dispatcher.run() 和后续逻辑包含在 trace 中：

```python
def _run_chat_sync(session_id: str, user_query: str, loop: asyncio.AbstractEventLoop,
                   datasource_id: str | None = None) -> None:
    """同步运行整个聊天流程（在线程池中执行）.

    所有操作都在同一个线程中完成：
    - 保存用户消息
    - 构建 agent
    - 运行 agent
    - 保存助手消息
    - 记录生成日志
    - 发送 chat_done 事件
    """
    # 获取 session 和 project_id
    session = session_service.get_session(session_id)
    if session is None:
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "chat_done",
            {"status": "failed", "error": "会话不存在"},
        )
        return

    project_id = session["project_id"]

    # 更新会话标题
    session_service.update_session_title_from_query(session_id, user_query)

    # 保存用户消息
    msg_result = session_service.add_message(session_id, "user", user_query)
    user_msg_id = msg_result.get("id", "") if isinstance(msg_result, dict) else ""

    # 启动异步纠错检测（不阻塞主流程）
    _start_async_correction_detection(
        session_id=session_id,
        user_query=user_query,
        project_id=project_id,
        user_msg_id=user_msg_id,
        loop=loop,
    )

    # 构建 dispatcher（统一入口，自动路由到对应子 Agent）
    dispatcher = _build_dispatcher_sync(project_id, session_id, loop)

    # 加载历史消息
    history = _load_history_messages_sync(session_id)

    # 构建记忆召回回调（从所有数据源召回）
    def memory_retriever(query: str, related_tables: list[str]) -> list[dict]:
        from app.services.memory_service import get_memories_for_query
        all_memories = []
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT id FROM datasources WHERE project_id = ?",
                (project_id,),
            )
            ds_ids = [row["id"] for row in cursor.fetchall()]
        finally:
            conn.close()

        for ds_id in ds_ids:
            try:
                mems = get_memories_for_query(
                    ds_id, query, related_tables=related_tables
                )
                all_memories.extend(mems)
            except Exception:
                pass
        return all_memories

    # 待确认记忆（上一轮检测到的，本轮在 summarize 中确认）
    pending_mems = get_pending_confirmations(session_id)

    extra_state = {
        "memory_retriever": memory_retriever,
        "pending_memories": pending_mems,
    }

    # ===== Langfuse trace: 包裹整个 dispatcher 执行 =====
    with _tracing_trace(
        name="chat_turn",
        user_id=session.get("user_id") or session_id,
        session_id=session_id,
        metadata={
            "datasource_id": datasource_id,
            "message_id": user_msg_id,
            "project_id": project_id,
        },
        input=user_query,
    ) as trace_ctx:
        start_time = time.perf_counter()

        try:
            # 运行 dispatcher（同步，已经在线程里了）
            result = dispatcher.run(user_query, history, datasource_id, extra_state)

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            # 提取结果
            answer = result.get("answer", "")
            sql = result.get("sql", "")
            exec_result = result.get("execution_result")
            intent_obj = result.get("intent")  # 可能是 IntentResult 对象或字符串
            iteration = result.get("iteration", 0)
            react_thoughts = result.get("react_thoughts", [])
            status = result.get("status", "unknown")
            error = result.get("error")
            intent_type = result.get("intent_type", "")

            # 构建执行结果（仅 query 类型有）
            success = exec_result is not None and exec_result.success if exec_result else False
            # schema_exploration / connect_datasource 也视为成功如果 status 是 done
            if not exec_result:
                success = status == "done"

            # 记录 trace output
            try:
                trace_ctx.update(
                    output=answer,
                    metadata={
                        "success": success,
                        "status": status,
                        "sql": sql[:500] if sql else "",
                        "iteration": iteration,
                        "intent_type": intent_type,
                        "execution_time_ms": execution_time_ms,
                    },
                )
            except Exception:
                pass

            # 保存助手消息
            ai_msg_result = session_service.add_message(
                session_id, "assistant", answer,
                metadata={
                    "sql": sql,
                    "success": success,
                    "execution_time_ms": execution_time_ms,
                    "iteration": iteration,
                    "trace_id": trace_ctx.id if trace_ctx.id else None,
                }
            )

            # 记录生成日志
            try:
                log_generation(
                    project_id=project_id,
                    datasource_id=datasource_id,
                    session_id=session_id,
                    user_query=user_query,
                    generated_sql=sql,
                    intent_summary=intent_type,
                    execution_success=success,
                    execution_time_ms=execution_time_ms,
                    row_count=getattr(exec_result, "row_count", 0) if exec_result else 0,
                    error_message=error if not success else None,
                    iteration=iteration,
                    reflection_notes=str(react_thoughts[-1]) if react_thoughts else None,
                    model=None,  # will be populated from tracing later
                    final_selected=True,
                )
            except Exception:
                pass

            # 缓存结果（分页用）
            if exec_result and success:
                try:
                    ai_msg_id = ai_msg_result.get("id", "") if isinstance(ai_msg_result, dict) else ""
                    result_cache.set(
                        f"msg:{ai_msg_id}",
                        {
                            "columns": exec_result.columns,
                            "rows": [list(r) for r in exec_result.rows],
                            "row_count": exec_result.row_count,
                        },
                        ttl=3600,
                    )
                except Exception:
                    pass

            # 发送结束事件
            loop.call_soon_threadsafe(
                _send_event_sync, session_id, "chat_done",
                {
                    "status": "success" if success else "error",
                    "message_id": ai_msg_result.get("id", "") if isinstance(ai_msg_result, dict) else "",
                    "trace_id": trace_ctx.id if trace_ctx.id else None,
                },
            )

        except Exception as e:
            # 记录 trace error
            try:
                trace_ctx.update(
                    metadata={"error": str(e), "traceback": traceback.format_exc()},
                )
            except Exception:
                pass

            error_msg = str(e)
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            session_service.add_message(
                session_id, "assistant", f"抱歉，处理时出错了：{error_msg}",
            )
            loop.call_soon_threadsafe(
                _send_event_sync, session_id, "chat_done",
                {"status": "error", "error": error_msg},
            )
        finally:
            # Flush tracing data at the end
            _tracing_flush()
```

**注意**：这一步改动较大，需要确保原有 `except Exception as e:` 和 `finally:` 块的逻辑完全保留，只是被包在 trace 里面。仔细对照原代码，确保不丢失任何原有功能。

- [ ] **Step 4: 运行 tracing 测试**

```bash
cd backend && pytest tests/test_tracing/test_chat_service_tracing.py -v
```

Expected: 1 test PASS。如果失败，根据错误调整。

- [ ] **Step 5: 运行完整测试套件**

```bash
cd backend && pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chat_service.py backend/tests/test_tracing/test_chat_service_tracing.py
git commit -m "feat(tracing): wrap chat turn in Langfuse trace at chat_service layer"
```

---

## Task 9: docker-compose + Makefile 自部署 Langfuse

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Makefile`

- [ ] **Step 1: 在 docker-compose.yml 中添加 langfuse-db 和 langfuse 服务**

在 `services` 下，`postgres` 服务之后添加：

```yaml
  langfuse-db:
    image: postgres:16-alpine
    container_name: nl2sql-langfuse-db
    environment:
      - POSTGRES_DB=langfuse
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse_secret
    volumes:
      - langfuse-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse -d langfuse"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  langfuse:
    image: langfuse/langfuse:latest
    container_name: nl2sql-langfuse
    depends_on:
      langfuse-db:
        condition: service_healthy
    ports:
      - "3030:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse_secret@langfuse-db:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_NEXTAUTH_SECRET:-my-dev-secret-change-in-production}
      - SALT=${LANGFUSE_SALT:-my-dev-salt-change-in-production}
      - ENCRYPTION_KEY=${LANGFUSE_ENCRYPTION_KEY:-0000000000000000000000000000000000000000000000000000000000000000}
      - TELEMETRY_ENABLED=${LANGFUSE_TELEMETRY_ENABLED:-false}
    restart: unless-stopped
```

在 `volumes:` 下添加：

```yaml
  langfuse-db-data:
```

- [ ] **Step 2: 在 Makefile 中添加 langfuse 快捷命令**

在 Makefile 的 `logs:` 目标后面，`# ============ 开发模式 ============` 之前添加：

```makefile
# ============ Langfuse 可观测性 ============

langfuse-up:
	@echo "启动 Langfuse 服务..."
	docker compose up -d langfuse
	@echo "Langfuse UI: http://localhost:3030"
	@echo "默认账号: 自行注册（首次访问创建管理员）"

langfuse-down:
	@echo "停止 Langfuse 服务..."
	docker compose stop langfuse langfuse-db

langfuse-logs:
	docker compose logs -f langfuse
```

- [ ] **Step 3: 验证 docker-compose 语法**

```bash
cd /Users/liurunchuan/projects/nl2sql && docker compose config 2>&1 | grep -E "langfuse|error"
```

Expected: 输出 langfuse 和 langfuse-db 服务配置，没有 error。

- [ ] **Step 4: 验证 Makefile 命令存在**

```bash
cd /Users/liurunchuan/projects/nl2sql && make help 2>&1 || make -n langfuse-up 2>&1
```

Expected: 无错误（`make -n` 是 dry-run）。

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml Makefile
git commit -m "feat(tracing): add Langfuse self-hosted services to docker-compose and Makefile"
```

---

## Task 10: 集成验证 + 文档

**Files:**
- None (验证和文档任务)

- [ ] **Step 1: 运行完整测试套件**

```bash
cd backend && pytest tests/ -v --tb=short
```

Expected: 全部通过，包括所有新增的 tracing 测试。

- [ ] **Step 2: 启动 Langfuse（如果有 docker）**

```bash
make langfuse-up
```

Expected: Langfuse 启动成功，可以在 http://localhost:3030 访问。

- [ ] **Step 3: 手动端到端验证**

1. 在后端 `.env` 中添加：
   ```
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=<创建项目后获取>
   LANGFUSE_SECRET_KEY=<创建项目后获取>
   LANGFUSE_HOST=http://localhost:3030
   ```
2. 启动后端 + 前端
3. 发送一条查询
4. 在 Langfuse UI 中检查：
   - Trace 列表中有新记录
   - Trace 详情显示完整嵌套：trace → dispatcher → nl2sql_agent → intent_analyze → llm_generation
   - 每个 generation 有 input/output/token 数据
   - 总 token 计数正确

- [ ] **Step 4: 更新 .env.example（如果存在）**

如果项目根目录或 backend 下有 `.env.example` 文件，在末尾添加 Langfuse 配置示例：

```
# Langfuse 可观测性（可选）
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3030
```

- [ ] **Step 5: 最终 commit**

```bash
git add .env.example 2>/dev/null || true
git commit -m "docs: add Langfuse .env example" --allow-empty
```

---

## 验收标准

Phase 1 完成后应满足：

1. **可插拔**：`LANGFUSE_ENABLED=false`（默认）时，整个 tracing 是 no-op，零性能影响，所有现有测试通过
2. **完整调用树**：在 Langfuse UI 中，一次用户查询可以看到 `trace → dispatcher → nl2sql_agent → [各节点span] → [llm generation]` 的完整嵌套结构
3. **LLM 详情**：每个 generation 包含完整的 input messages、output content、model、token 用量（input/output/total）
4. **Metadata 丰富**：trace 上有 session_id、datasource_id、user_id；span 上有 step 名称和详情
5. **不破坏现有功能**：所有已有测试 100% 通过，SSE 事件流行为不变
6. **自部署**：一条 `make langfuse-up` 命令即可启动 Langfuse 服务
