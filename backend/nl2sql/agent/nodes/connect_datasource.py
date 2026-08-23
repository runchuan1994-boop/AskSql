"""Connect datasource node: agentic datasource onboarding via tool calling.

This node uses the LLM's tool-calling capability to drive the datasource
creation workflow: create → test connection → import schema.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole, ToolCall, ToolCallResult
from nl2sql.llm.factory import create_llm_client

from ..tools.datasource_tools import DATASOURCE_TOOLS, execute_datasource_tool

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CONNECT_DS_SYSTEM_PROMPT = """你是一个数据源连接助手，负责帮助用户创建并配置数据源。

你的任务：
1. 从用户消息中提取数据源连接信息（类型、主机、端口、数据库名、用户名、密码、名称等）。
2. 如果信息不足，请直接询问用户补充，不要调用工具。
3. 如果信息充足，按以下顺序操作：
   a. 调用 create_datasource 创建数据源
   b. 调用 test_connection 测试连接
   c. 如果连接成功，调用 import_schema 导入 Schema
4. 操作完成后，用自然语言向用户汇报结果。
5. 如果某一步失败，告知用户失败原因，不要继续后续步骤。

注意：
- 每一步只调用一个工具，等待结果后再决定下一步。
- 始终用用户的语言回答。
- 不要编造信息，所有操作都必须基于工具返回的真实结果。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def _extract_datasource_id_from_result(result: str) -> str | None:
    """Try to extract datasource ID from a create_datasource tool result string.

    The result format is:
        数据源创建成功：
          ID: xxx
          名称: ...
    """
    match = re.search(r"ID:\s*(\S+)", result)
    if match:
        return match.group(1).strip()
    return None


def _extract_table_count_from_result(result: str) -> int:
    """Try to extract the imported table count from import_schema result."""
    match = re.search(r"共\s*(\d+)\s*张表", result)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 0


# ---------------------------------------------------------------------------
# Event mapping for tool calls
# ---------------------------------------------------------------------------

# Map tool_name -> (start_event, success_event, failure_event)
_TOOL_EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "create_datasource": ("ds_creating", "ds_created", "ds_create_failed"),
    "test_connection": ("ds_testing", "ds_connected", "ds_connection_failed"),
    "import_schema": ("ds_importing", "ds_imported", "ds_import_failed"),
}


def _send_tool_start_event(state: dict, tool_name: str, args: dict) -> None:
    """Send SSE event indicating a tool is about to be called."""
    events = _TOOL_EVENT_MAP.get(tool_name)
    if events is None:
        return
    _send_event(state, events[0], {"tool": tool_name, "args": args})


def _send_tool_end_event(state: dict, tool_name: str, result: str, success: bool) -> None:
    """Send SSE event indicating a tool call has completed."""
    events = _TOOL_EVENT_MAP.get(tool_name)
    if events is None:
        return
    event_type = events[1] if success else events[2]
    _send_event(state, event_type, {"tool": tool_name, "result": result})


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def connect_datasource_node(state: dict) -> dict:
    """Agentic datasource connection node using LLM tool calling.

    Drives the create → test → import workflow via multi-round tool calls.

    Returns:
        dict with final_answer, status, datasource_id, tables_imported
    """
    project_id = state["project_id"]
    user_query = state["user_query"]
    intent = state.get("intent")

    # Build user message with any pre-extracted datasource info
    datasource_info = {}
    if intent and hasattr(intent, "datasource_info") and intent.datasource_info:
        datasource_info = intent.datasource_info

    user_msg_parts = [f"用户请求：{user_query}"]
    if datasource_info:
        info_lines = [f"  {k}: {v}" for k, v in datasource_info.items() if v]
        if info_lines:
            user_msg_parts.append("")
            user_msg_parts.append("从用户消息中提取到的连接信息：")
            user_msg_parts.extend(info_lines)

    user_msg = "\n".join(user_msg_parts)

    messages: list[Message] = [
        Message(role=MessageRole.SYSTEM, content=CONNECT_DS_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_msg),
    ]

    llm = create_llm_client()
    tools = DATASOURCE_TOOLS

    max_iterations = 4
    iteration = 0
    datasource_id: str | None = None
    tables_imported = 0
    final_answer = ""
    status = "done"

    while iteration < max_iterations:
        iteration += 1

        response = llm.chat(messages, tools=tools, temperature=0.0)

        if not response.tool_calls:
            # LLM returned a plain text answer - we're done
            final_answer = response.content.strip()
            messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content,
            ))
            break

        # Add assistant message with tool calls to conversation
        messages.append(Message(
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            tool_calls=list(response.tool_calls),
        ))

        # Execute each tool call and add tool result messages
        for tool_call in response.tool_calls:
            tool_name = tool_call.name
            tool_args = tool_call.arguments or {}

            # Send start event
            _send_tool_start_event(state, tool_name, tool_args)

            # Execute the tool
            try:
                tool_result_str = execute_datasource_tool(
                    tool_name, tool_args, project_id
                )
            except Exception as e:
                tool_result_str = f"工具执行异常: {e}"

            # Determine success/failure for event purposes
            is_success = not (
                "失败" in tool_result_str
                or "错误" in tool_result_str
                or "异常" in tool_result_str
                or "not found" in tool_result_str.lower()
            )

            # Send end event
            _send_tool_end_event(state, tool_name, tool_result_str, is_success)

            # Track datasource_id from create_datasource result
            if tool_name == "create_datasource" and is_success:
                extracted_id = _extract_datasource_id_from_result(tool_result_str)
                if extracted_id:
                    datasource_id = extracted_id

            # Track table count from import_schema result
            if tool_name == "import_schema" and is_success:
                tables_imported = _extract_table_count_from_result(tool_result_str)

            # Add tool result message
            messages.append(Message(
                role=MessageRole.TOOL,
                tool_result=ToolCallResult(
                    tool_call_id=tool_call.id,
                    name=tool_name,
                    content=tool_result_str,
                ),
            ))

    else:
        # Loop exited via max iterations (not via break)
        status = "failed"
        final_answer = "抱歉，数据源连接过程超过了最大迭代次数，请稍后再试。"

    # Send final result event
    _send_event(state, "final_result", {
        "answer": final_answer,
        "success": status == "done",
        "datasource_id": datasource_id,
        "tables_imported": tables_imported,
    })
    _send_event(state, "done", {"status": status})

    return {
        "final_answer": final_answer,
        "status": status,
        "datasource_id": datasource_id,
        "tables_imported": tables_imported,
    }
