"""Tests for LLM message models."""
from __future__ import annotations

import pytest

from nl2sql.llm.message import (
    Message,
    MessageRole,
    TextContent,
    ToolCall,
    ToolCallResult,
)


class TestMessageRole:
    def test_has_all_expected_roles(self):
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"

    def test_is_string_enum(self):
        assert str(MessageRole.SYSTEM) == "system"


class TestToolCall:
    def test_creation(self):
        tc = ToolCall(id="call_123", name="get_schema", arguments={"table": "users"})
        assert tc.id == "call_123"
        assert tc.name == "get_schema"
        assert tc.arguments == {"table": "users"}

    def test_arguments_default_empty_dict(self):
        tc = ToolCall(id="call_1", name="foo")
        assert tc.arguments == {}


class TestToolCallResult:
    def test_creation(self):
        tcr = ToolCallResult(tool_call_id="call_123", name="get_schema", content='{"rows": 5}')
        assert tcr.tool_call_id == "call_123"
        assert tcr.name == "get_schema"
        assert tcr.content == '{"rows": 5}'


class TestTextContent:
    def test_creation(self):
        tc = TextContent(text="Hello")
        assert tc.text == "Hello"
        assert tc.type == "text"

    def test_type_is_always_text(self):
        tc = TextContent(text="hi")
        assert tc.type == "text"


class TestMessage:
    def test_system_message(self):
        msg = Message(role=MessageRole.SYSTEM, content="You are helpful.")
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are helpful."
        assert msg.tool_calls == []
        assert msg.tool_result is None

    def test_user_message_defaults(self):
        msg = Message(role=MessageRole.USER, content="Hi")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hi"
        assert msg.tool_calls == []
        assert msg.tool_result is None

    def test_assistant_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="exec_sql", arguments={"sql": "SELECT 1"})
        msg = Message(role=MessageRole.ASSISTANT, tool_calls=[tc])
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == ""
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "call_1"

    def test_tool_message_with_result(self):
        tcr = ToolCallResult(tool_call_id="call_1", name="exec_sql", content="[]")
        msg = Message(role=MessageRole.TOOL, tool_result=tcr)
        assert msg.role == MessageRole.TOOL
        assert msg.tool_result is not None
        assert msg.tool_result.tool_call_id == "call_1"
