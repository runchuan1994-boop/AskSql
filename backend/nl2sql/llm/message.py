"""LLM message models."""
from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Role of a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A tool call from the assistant."""

    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """The result of a tool call, used in tool role messages."""

    tool_call_id: str
    name: str
    content: str


class TextContent(BaseModel):
    """Text content block in a message."""

    text: str
    type: str = "text"


class Message(BaseModel):
    """A single chat message."""

    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: Optional[ToolCallResult] = None
