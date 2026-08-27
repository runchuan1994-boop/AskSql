"""Anthropic Claude LLM client."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from anthropic import Anthropic

from .base import ChatChunk, ChatResponse, LLMClient
from .message import Message, MessageRole, ToolCall, ToolCallResult


class ClaudeClient(LLMClient):
    """Client for Anthropic Claude API."""

    provider = "anthropic"

    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self.model = model

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict], str]:
        """Convert internal Message objects to Anthropic format.

        Returns (messages_list, system_prompt).
        """
        system_parts: list[str] = []
        anthropic_messages: list[dict] = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                if msg.content:
                    system_parts.append(msg.content)
                continue

            if msg.role == MessageRole.USER:
                anthropic_messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT:
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({
                        "type": "text",
                        "text": msg.content,
                    })
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else "",
                })
            elif msg.role == MessageRole.TOOL and msg.tool_result is not None:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_result.tool_call_id,
                        "content": msg.tool_result.content,
                    }],
                })

        system_prompt = "\n".join(system_parts)
        return anthropic_messages, system_prompt

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI-format tools to Anthropic format."""
        anthropic_tools: list[dict] = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return anthropic_tools

    def _parse_tool_calls(self, content_blocks: list[Any]) -> list[ToolCall]:
        """Parse tool calls from Anthropic content blocks."""
        tool_calls: list[ToolCall] = []
        for block in content_blocks:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=dict(block.input),
                ))
        return tool_calls

    def _chat_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        anthropic_messages, system_prompt = self._convert_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return ChatResponse(
            content="".join(text_parts),
            tool_calls=self._parse_tool_calls(response.content),
            model=response.model,
            usage=usage,
        )

    def _chat_stream_impl(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        anthropic_messages, system_prompt = self._convert_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield ChatChunk(content_delta=text, done=False)
            final_message = stream.get_final_message()
            # Emit tool calls from final message
            tool_calls = self._parse_tool_calls(final_message.content)
            for tc in tool_calls:
                yield ChatChunk(tool_call_delta=tc, done=False)
            yield ChatChunk(done=True)
