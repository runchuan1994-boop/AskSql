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
