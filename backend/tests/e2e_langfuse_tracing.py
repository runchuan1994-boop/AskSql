#!/usr/bin/env python3
"""
End-to-end Langfuse tracing verification script.

Usage:
  LANGFUSE_PUBLIC_KEY=pk-xxx LANGFUSE_SECRET_KEY=sk-xxx LANGFUSE_HOST=http://localhost:3030 \
  python tests/e2e_langfuse_tracing.py

Steps:
  1. Verify Langfuse connection
  2. Start a chat query via the backend API
  3. Wait for the trace to appear in Langfuse
  4. Verify the trace structure: trace → spans → generations
  5. Print results
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

import requests


LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3030")
PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# Test query
TEST_QUERY = "总共有多少用户？"
TEST_SESSION = "e2e_test_session_" + str(int(time.time()))


def step(desc: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    print(f"  ❌ {msg}")
    sys.exit(1)


def info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


# ---------------------------------------------------------------------------
# Step 1: Verify Langfuse connection
# ---------------------------------------------------------------------------
step("Step 1: 验证 Langfuse 连接")

if not PUBLIC_KEY or not SECRET_KEY:
    fail("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未设置")

health = requests.get(f"{LANGFUSE_HOST}/api/public/health", timeout=10)
if health.status_code != 200:
    fail(f"Langfuse 健康检查失败: {health.status_code}")
ok(f"Langfuse 健康检查通过: {LANGFUSE_HOST}")

# 用 SDK 的方式验证 key 有效性（调用一个简单的 API）
auth = (PUBLIC_KEY, SECRET_KEY)
try:
    resp = requests.get(f"{LANGFUSE_HOST}/api/public/projects", auth=auth, timeout=10)
    if resp.status_code != 200:
        fail(f"API Key 验证失败: {resp.status_code} {resp.text[:200]}")
    projects = resp.json().get("data", [])
    ok(f"API Key 有效，当前项目数: {len(projects)}")
except Exception as e:
    fail(f"Langfuse API 调用失败: {e}")


# ---------------------------------------------------------------------------
# Step 2: 检查后端是否可用
# ---------------------------------------------------------------------------
step("Step 2: 验证后端服务")

try:
    health_resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
    if health_resp.status_code != 200:
        fail(f"后端健康检查失败: {health_resp.status_code}")
    ok("后端服务运行正常")
except requests.ConnectionError:
    fail(f"无法连接到后端: {BACKEND_URL}  (请先启动后端)")
except Exception as e:
    fail(f"后端检查出错: {e}")


# ---------------------------------------------------------------------------
# Step 3: 获取当前 trace 数量（基准）
# ---------------------------------------------------------------------------
step("Step 3: 获取当前 Langfuse trace 数量（基准）")

before_count = 0
try:
    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces",
        auth=auth,
        params={"page": 1, "limit": 1},
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        before_count = data.get("meta", {}).get("totalItems", 0)
    ok(f"当前 trace 数量: {before_count}")
except Exception as e:
    info(f"获取 trace 列表失败（不影响测试，继续）: {e}")


# ---------------------------------------------------------------------------
# Step 4: 发起一条聊天查询
# ---------------------------------------------------------------------------
step("Step 4: 发起聊天查询")

# 先创建 session（或者直接发 chat 请求）
info(f"测试查询: '{TEST_QUERY}'")
info(f"测试会话: {TEST_SESSION}")

# 发送聊天请求
start_time = time.time()
try:
    resp = requests.post(
        f"{BACKEND_URL}/api/chat",
        json={
            "session_id": TEST_SESSION,
            "message": TEST_QUERY,
        },
        timeout=120,  # 首次查询可能比较慢
    )
    if resp.status_code not in (200, 202):
        fail(f"聊天请求失败: {resp.status_code} {resp.text[:500]}")

    # 消费 SSE 流等待完成
    with requests.get(
        f"{BACKEND_URL}/api/chat/stream/{TEST_SESSION}",
        stream=True,
        timeout=120,
    ) as stream_resp:
        chat_done = False
        for line in stream_resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                event_data = line[6:]
                if '"type":"chat_done"' in event_data or '"chat_done"' in event_data:
                    chat_done = True
                    info(f"收到 chat_done 事件")
                    break
                if '"type":"error"' in event_data:
                    fail(f"查询出错: {event_data[:200]}")

        if not chat_done:
            # 再等一下
            time.sleep(3)

    elapsed = round(time.time() - start_time, 1)
    ok(f"查询完成，耗时 {elapsed}s")
except Exception as e:
    fail(f"聊天请求异常: {e}")


# ---------------------------------------------------------------------------
# Step 5: 等待 trace 上报到 Langfuse
# ---------------------------------------------------------------------------
step("Step 5: 等待 trace 上报到 Langfuse")

# Langfuse SDK 是异步批量上报的，需要等一下
max_wait = 60
waited = 0
trace_found = None

while waited < max_wait:
    try:
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            auth=auth,
            params={"page": 1, "limit": 10},
            timeout=10,
        )
        if resp.status_code == 200:
            traces = resp.json().get("data", [])
            # 找我们这次测试产生的 trace（按 session_id 匹配）
            for t in traces:
                if t.get("sessionId") == TEST_SESSION or t.get("name") == "chat_turn":
                    # 再检查 input 是否匹配
                    trace_input = t.get("input", "")
                    if isinstance(trace_input, str) and TEST_QUERY in trace_input:
                        trace_found = t
                        break
                    # 如果 session_id 匹配也算
                    if t.get("sessionId") == TEST_SESSION:
                        trace_found = t
                        break

            if trace_found:
                break
    except Exception:
        pass

    time.sleep(3)
    waited += 3
    print(f"  等待中... {waited}s", end="\r")

print()  # newline

if not trace_found:
    fail(f"{max_wait}s 内未在 Langfuse 中找到测试 trace")

trace_id = trace_found.get("id")
ok(f"Trace 已找到: {trace_id}")


# ---------------------------------------------------------------------------
# Step 6: 验证 trace 详情
# ---------------------------------------------------------------------------
step("Step 6: 验证 trace 详情")

try:
    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces/{trace_id}",
        auth=auth,
        timeout=10,
    )
    if resp.status_code != 200:
        fail(f"获取 trace 详情失败: {resp.status_code}")
    trace_detail = resp.json()
except Exception as e:
    fail(f"获取 trace 详情异常: {e}")

# 验证基本字段
assertions = []

# name
if trace_detail.get("name") == "chat_turn":
    ok("trace.name == 'chat_turn'")
else:
    assertions.append(f"trace.name 不对: {trace_detail.get('name')}")

# sessionId
if trace_detail.get("sessionId") == TEST_SESSION:
    ok(f"trace.sessionId == '{TEST_SESSION}'")
else:
    assertions.append(f"sessionId 不对: {trace_detail.get('sessionId')}")

# input
trace_input = trace_detail.get("input", "")
if TEST_QUERY in str(trace_input):
    ok(f"trace.input 包含查询内容")
else:
    assertions.append(f"input 不对: {str(trace_input)[:100]}")

# output 不为空
if trace_detail.get("output"):
    ok("trace.output 非空（有回答内容）")
else:
    assertions.append("trace.output 为空")

# metadata
metadata = trace_detail.get("metadata", {}) or {}
if metadata.get("datasource_id") or metadata.get("project_id"):
    ok(f"trace.metadata 包含业务元数据: {list(metadata.keys())}")
else:
    assertions.append(f"metadata 缺少业务字段: {metadata}")


# ---------------------------------------------------------------------------
# Step 7: 验证 span 结构
# ---------------------------------------------------------------------------
step("Step 7: 验证 span / observation 结构")

# 获取 trace 的所有 observations（spans + generations）
try:
    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces/{trace_id}/observations",
        auth=auth,
        params={"page": 1, "limit": 50},
        timeout=10,
    )
    if resp.status_code != 200:
        fail(f"获取 observations 失败: {resp.status_code}")
    observations = resp.json().get("data", [])
except Exception as e:
    fail(f"获取 observations 异常: {e}")

ok(f"共 {len(observations)} 个 observation（span + generation）")

# 分类统计
spans = [o for o in observations if o.get("type") == "SPAN"]
generations = [o for o in observations if o.get("type") == "GENERATION"]
events = [o for o in observations if o.get("type") == "EVENT"]

print(f"    - SPAN:         {len(spans)} 个")
print(f"    - GENERATION:   {len(generations)} 个")
print(f"    - EVENT:        {len(events)} 个")

# 验证有 dispatcher span
dispatcher_spans = [s for s in spans if "dispatcher" in s.get("name", "").lower()]
if dispatcher_spans:
    ok(f"找到 dispatcher span: {dispatcher_spans[0]['name']}")
else:
    span_names = [s.get("name") for s in spans]
    assertions.append(f"未找到 dispatcher span，所有 span: {span_names}")

# 验证有 LLM generation
if len(generations) >= 1:
    ok(f"至少有 1 个 LLM generation（实际 {len(generations)} 个）")
else:
    assertions.append("没有找到任何 GENERATION 类型的 observation")

# 验证 generation 有 model 和 usage
for gen in generations[:1]:  # 只检查第一个
    model = gen.get("model", "")
    usage = gen.get("usage", {}) or {}
    if model:
        ok(f"generation.model: {model}")
    else:
        assertions.append("generation 没有 model 字段")

    # usage 可能在不同的字段里
    input_tokens = usage.get("inputTokens") or usage.get("prompt_tokens") or usage.get("input")
    output_tokens = usage.get("outputTokens") or usage.get("completion_tokens") or usage.get("output")
    if input_tokens or output_tokens:
        ok(f"generation.usage: input={input_tokens}, output={output_tokens}")
    else:
        assertions.append(f"generation 没有 token 使用量: {usage}")
    break


# ---------------------------------------------------------------------------
# Step 8: 汇总结果
# ---------------------------------------------------------------------------
step("✅ 端到端测试结果汇总")

total_checks = 8  # 大致统计
passed = total_checks - len(assertions)

if assertions:
    print(f"\n  ⚠️  {len(assertions)} 项警告/未通过:")
    for a in assertions:
        print(f"     - {a}")
    print()

if len(assertions) == 0:
    print("\n  🎉 所有检查通过！Langfuse 追踪链路完整工作！\n")
    print(f"  Trace ID:   {trace_id}")
    print(f"  Trace URL:  {LANGFUSE_HOST}/trace/{trace_id}")
    print(f"  Spans:      {len(spans)}")
    print(f"  Gens:       {len(generations)}")
    print()
    sys.exit(0)
else:
    print(f"\n  ⚠️  部分检查未通过（{passed}/{total_checks}），请查看上方详情\n")
    print(f"  Trace ID:   {trace_id}")
    print(f"  Trace URL:  {LANGFUSE_HOST}/trace/{trace_id}")
    print()
    sys.exit(1)
