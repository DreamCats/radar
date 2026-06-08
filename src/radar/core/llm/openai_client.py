from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from radar.core.llm.client import ChatMessage, LlmToolSpec, RuntimeLlmProvider

from radar.core.llm.client import LlmChatResponse, LlmToolCall


def chat_openai(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
) -> str:
    """OpenAI Chat Completions 协议，兼容大多数 OpenAI-like 网关。"""

    return chat_openai_response(
        provider,
        messages,
        model,
        temperature,
        max_tokens,
        disable_thinking,
    ).content


def chat_openai_response(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
    tools: list["LlmToolSpec"] | None = None,
) -> LlmChatResponse:
    """OpenAI Chat Completions 响应，包含文本和 tool calls。"""

    _ = disable_thinking
    payload = _payload(provider, messages, model, temperature, max_tokens, tools)

    with httpx.Client(timeout=provider.timeout) as client:
        response = client.post(
            _chat_completions_url(provider.base_url),
            headers=_headers(provider),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    message = _first_message(data)
    if not message:
        return LlmChatResponse(content="", tool_calls=[])

    content = message.get("content")
    return LlmChatResponse(
        content=content if isinstance(content, str) else "",
        tool_calls=_parse_tool_calls(message),
    )


def _payload(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    tools: list["LlmToolSpec"] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {"model": model or provider.model, "messages": messages}
    effective_temperature = temperature if temperature is not None else provider.temperature
    if effective_temperature is not None:
        payload["temperature"] = effective_temperature
    effective_max_tokens = max_tokens or provider.max_tokens
    if effective_max_tokens:
        payload["max_tokens"] = effective_max_tokens
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]
    return payload


def _first_message(data: object) -> dict | None:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices, list):
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    return message


def _parse_tool_calls(message: dict) -> list[LlmToolCall]:
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[LlmToolCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        arguments = function.get("arguments")
        calls.append(
            LlmToolCall(
                call_id=str(raw_call.get("id") or name),
                name=name,
                arguments=_parse_arguments(arguments),
            )
        )
    return calls


def _parse_arguments(arguments: object) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _chat_completions_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    return f"{trimmed}/v1/chat/completions"


def _headers(provider: "RuntimeLlmProvider") -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider.api_key}",
        **provider.headers,
    }
