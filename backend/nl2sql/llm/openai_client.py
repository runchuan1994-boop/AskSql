"""OpenAI-compatible LLM client."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from .base import ChatChunk, ChatResponse, LLMClient
from .message import Message, MessageRole, ToolCall, ToolCallResult


class OpenAIClient(LLMClient):
    """Client for OpenAI-compatible APIs (official OpenAI and local models)."""

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal Message objects to OpenAI message format."""
        result: list[dict] = []
        for msg in messages:
            if msg.role == MessageRole.TOOL and msg.tool_result is not None:
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_result.tool_call_id,
                    "content": msg.tool_result.content,
                })
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                openai_tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                entry: dict[str, Any] = {"role": "assistant", "tool_calls": openai_tool_calls}
                if msg.content:
                    entry["content"] = msg.content
                result.append(entry)
            else:
                result.append({
                    "role": str(msg.role),
                    "content": msg.content,
                })
        return result

    def _parse_tool_calls(self, response: Any) -> list[ToolCall]:
        """Parse tool calls from an OpenAI response."""
        tool_calls: list[ToolCall] = []
        message = response.choices[0].message
        if not getattr(message, "tool_calls", None):
            return tool_calls
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            ))
        return tool_calls

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return ChatResponse(
            content=content,
            tool_calls=self._parse_tool_calls(response),
            model=response.model,
            usage=usage,
        )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        stream = self._client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                content_delta = delta.content or ""
                tool_call_delta = None
                if getattr(delta, "tool_calls", None):
                    # First chunk of a tool call has full id/name, subsequent have args fragments
                    for tc_delta in delta.tool_calls:
                        tc_id = getattr(tc_delta, "id", "") or ""
                        tc_name = getattr(tc_delta.function, "name", "") if tc_delta.function else ""
                        tc_args_str = getattr(tc_delta.function, "arguments", "") if tc_delta.function else ""
                        try:
                            tc_args = json.loads(tc_args_str) if tc_args_str else {}
                        except json.JSONDecodeError:
                            tc_args = {}
                        # Only emit tool call delta on first occurrence (with id) or if there's content
                        if tc_id or tc_name or tc_args_str:
                            tool_call_delta = ToolCall(
                                id=tc_id,
                                name=tc_name,
                                arguments=tc_args,
                            )
                yield ChatChunk(
                    content_delta=content_delta,
                    tool_call_delta=tool_call_delta,
                    done=False,
                )
            if chunk.choices and chunk.choices[0].finish_reason:
                yield ChatChunk(done=True)
                return
