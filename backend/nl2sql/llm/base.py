"""LLM client abstract base class and response models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Optional

from pydantic import BaseModel, Field

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
    """Abstract base class for LLM clients."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a non-streaming chat request."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        """Send a streaming chat request, yielding ChatChunk objects."""
        ...
