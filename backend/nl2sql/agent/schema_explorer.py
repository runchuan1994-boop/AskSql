"""Schema Explorer Agent: 专门用于数据库 schema 探索和数据理解.

这个 Agent 回答关于数据库结构的问题，比如：
- "这个库里有什么表？"
- "users 表有哪些列？"
- "status 字段有哪些取值？"
- "orders 表有多少行数据？"

它使用 tool calling 驱动一系列 schema/探查工具来获取信息，
然后用自然语言总结给用户。
"""
from __future__ import annotations

from typing import Callable

from nl2sql.llm import Message, MessageRole, ToolCall, ToolCallResult
from nl2sql.llm.factory import create_llm_client

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SCHEMA_EXPLORER_SYSTEM_PROMPT = """你是一位数据库 schema 探索专家，帮助用户了解数据库的结构和数据特征。

你的能力：
1. list_tables - 列出所有表名和描述
2. describe_table - 查看某张表的详细结构（列、类型、键、描述）
3. probe_sample - 抽样查看表的数据
4. probe_distinct - 查看某列的不重复值（适合分类字段）
5. probe_min_max - 查看某列的最小值和最大值
6. probe_count - 查看表的总行数

工作方式：
- 先理解用户想知道什么
- 调用合适的工具获取信息
- 拿到信息后用自然语言回答用户
- 如果一次工具调用不够，可以多次调用
- 始终用用户的语言回答

注意事项：
- 不要编造信息，所有回答必须基于工具返回的真实数据
- 如果用户问的问题你回答不了，直接说明
- 回答要简洁明了，突出关键信息
- 表名、列名等技术名词用原文显示
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SchemaExplorerAgent:
    """Schema 探索 Agent.

    使用 tool calling 驱动 schema 探查流程。

    用法:
    ```python
    agent = SchemaExplorerAgent(
        datasources=[datasource_schema],
        executors={"ds_id": executor},
        event_callback=my_callback,
    )
    result = agent.run("users 表有哪些列？")
    print(result["answer"])
    ```
    """

    def __init__(
        self,
        datasources: list,
        executors: dict,
        event_callback: Callable[[str, dict], None] | None = None,
        max_iterations: int = 5,
        step_logger=None,
    ):
        self.datasources = datasources
        self.executors = executors
        self.event_callback = event_callback
        self.max_iterations = max_iterations
        self._step_logger = step_logger  # 可选：步骤耗时记录器（鸭子类型）

    def _send_event(self, event_type: str, data: dict | None = None) -> None:
        """Send an event via callback if set."""
        if self.event_callback is not None:
            try:
                self.event_callback(event_type, data or {})
            except Exception:
                pass

    def _build_tools(self) -> list[dict]:
        """构建可用工具列表（OpenAI function calling 格式）."""
        from nl2sql.agent.tools import (
            SCHEMA_TOOLS_DEFINITION,
            PROBE_TOOLS_DEFINITION,
        )
        return SCHEMA_TOOLS_DEFINITION + PROBE_TOOLS_DEFINITION

    def _execute_tool(self, tool_name: str, args: dict, state_proxy: dict) -> str:
        """执行一个工具调用，返回字符串结果."""
        from nl2sql.agent.tools import (
            PROBE_TOOL_FUNCTIONS,
            describe_table,
            list_tables,
        )

        # Schema tools
        if tool_name == "list_tables":
            return list_tables(state_proxy, args.get("datasource_id"))
        if tool_name == "describe_table":
            return describe_table(
                state_proxy,
                args.get("table_name", ""),
                args.get("datasource_id"),
            )

        # Probe tools
        if tool_name in PROBE_TOOL_FUNCTIONS:
            func = PROBE_TOOL_FUNCTIONS[tool_name]
            return func(state_proxy, **args)

        return f"未知工具: {tool_name}"

    def run(self, user_query: str, conversation_history: list | None = None) -> dict:
        """运行一次 schema 探索.

        Args:
            user_query: 用户的自然语言问题
            conversation_history: 历史对话消息列表

        Returns:
            结果字典: {answer, status, tool_calls_count, error?}
        """
        # 构造一个 state proxy 对象，让工具函数能访问 datasources 和 executors
        # 工具函数用 state["datasources"] 和 state["datasource_executors"] 访问
        state_proxy = _StateProxy(
            datasources=self.datasources,
            datasource_executors=self.executors,
        )

        messages: list[Message] = [
            Message(role=MessageRole.SYSTEM, content=SCHEMA_EXPLORER_SYSTEM_PROMPT),
        ]

        # 加入历史消息（去掉 system）
        if conversation_history:
            for msg in conversation_history[-10:]:
                if hasattr(msg, "role") and msg.role != MessageRole.SYSTEM:
                    messages.append(msg)

        # 用户当前问题
        messages.append(Message(role=MessageRole.USER, content=user_query))

        self._send_event("schema_exploring", {"query": user_query})

        llm = create_llm_client()
        tools = self._build_tools()
        tool_calls_count = 0

        for iteration in range(self.max_iterations):
            response = llm.chat(messages, tools=tools, temperature=0.0)

            if not response.tool_calls:
                # LLM 返回了纯文本回答，结束
                answer = response.content.strip()
                self._send_event("schema_explore_done", {
                    "iterations": iteration + 1,
                    "tool_calls": tool_calls_count,
                })
                return {
                    "answer": answer,
                    "status": "done",
                    "tool_calls_count": tool_calls_count,
                }

            # 有 tool calls，执行它们
            messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content or "",
                tool_calls=list(response.tool_calls),
            ))

            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.arguments or {}
                tool_calls_count += 1

                self._send_event("schema_tool_call", {
                    "tool": tool_name,
                    "args": tool_args,
                })

                try:
                    result_str = self._execute_tool(tool_name, tool_args, state_proxy)
                except Exception as e:
                    result_str = f"工具执行错误: {e}"

                self._send_event("schema_tool_result", {
                    "tool": tool_name,
                    "success": "错误" not in result_str and "失败" not in result_str,
                })

                messages.append(Message(
                    role=MessageRole.TOOL,
                    tool_result=ToolCallResult(
                        tool_call_id=tool_call.id,
                        name=tool_name,
                        content=result_str,
                    ),
                ))

        # 达到最大迭代次数
        answer = "抱歉，schema 探索过程超过了最大迭代次数，请稍后再试。"
        return {
            "answer": answer,
            "status": "failed",
            "tool_calls_count": tool_calls_count,
            "error": "max iterations reached",
        }


# ---------------------------------------------------------------------------
# State proxy — 为工具函数提供类 state 的接口
# ---------------------------------------------------------------------------

class _StateProxy:
    """轻量代理对象，模拟 AgentState 的访问接口供工具函数使用.

    工具函数通过 state["datasources"] / state["datasource_executors"] 访问数据，
    这个 proxy 同时支持属性访问和字典访问。
    """

    def __init__(self, datasources: list, datasource_executors: dict):
        self.datasources = datasources
        self.datasource_executors = datasource_executors

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __contains__(self, key):
        return hasattr(self, key)
