from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from radar.core.llm.client import ChatMessage, LlmToolSpec, RuntimeLlmProvider

from radar.core.llm.client import (
    LlmChatDelta,
    LlmChatDone,
    LlmChatResponse,
    LlmChatStreamEvent,
    LlmReasoningDelta,
    LlmToolCall,
    LlmToolCallDelta,
    LlmToolCallDone,
    LlmToolCallStarted,
)


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
    enable_thinking: bool = False,
) -> LlmChatResponse:
    """OpenAI Chat Completions 响应，包含文本和 tool calls。"""

    _ = disable_thinking, enable_thinking
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
        return LlmChatResponse(content="", tool_calls=[], stop_reason=_first_finish_reason(data), usage=_usage(data))

    content = message.get("content")
    return LlmChatResponse(
        content=content if isinstance(content, str) else "",
        tool_calls=_parse_tool_calls(message),
        stop_reason=_first_finish_reason(data),
        usage=_usage(data),
    )


def stream_chat_openai_response(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
    tools: list["LlmToolSpec"] | None = None,
    enable_thinking: bool = False,
) -> Iterator[LlmChatStreamEvent]:
    """OpenAI Chat Completions SSE，边返回文本边聚合最终 tool calls。"""

    _ = disable_thinking, enable_thinking
    payload = _payload(provider, messages, model, temperature, max_tokens, tools)
    payload["stream"] = True
    content_parts: list[str] = []
    tool_call_parts: dict[int, dict[str, str]] = {}
    started_tool_call_indexes: set[int] = set()
    stop_reason: str | None = None

    with httpx.Client(timeout=provider.timeout) as client:
        with client.stream(
            "POST",
            _chat_completions_url(provider.base_url),
            headers={**_headers(provider), "Accept": "text/event-stream"},
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                chunk = _parse_stream_line(line)
                if chunk is None:
                    continue
                if chunk == "[DONE]":
                    break
                delta = _first_delta(chunk)
                stop_reason = _first_finish_reason(chunk) or stop_reason
                if delta is None:
                    continue
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(reasoning, str) and reasoning:
                    yield LlmReasoningDelta(content=reasoning)
                content = delta.get("content")
                if isinstance(content, str) and content:
                    content_parts.append(content)
                    yield LlmChatDelta(content=content)
                yield from _collect_tool_call_deltas(tool_call_parts, delta, started_tool_call_indexes)

    tool_call_items = _parse_stream_tool_call_items(tool_call_parts)
    for index, tool_call in tool_call_items:
        yield LlmToolCallDone(index=index, tool_call=tool_call)

    yield LlmChatDone(
        LlmChatResponse(
            content="".join(content_parts),
            tool_calls=[tool_call for _, tool_call in tool_call_items],
            stop_reason=stop_reason,
        )
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


def _parse_stream_line(line: str) -> object | None:
    text = line.strip()
    if not text or text.startswith(":"):
        return None
    if not text.startswith("data:"):
        return None
    data = text.removeprefix("data:").strip()
    if data == "[DONE]":
        return data
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _first_delta(data: object) -> dict | None:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices, list):
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    delta = first.get("delta")
    return delta if isinstance(delta, dict) else None


def _collect_tool_call_deltas(
    tool_call_parts: dict[int, dict[str, str]],
    delta: dict,
    started_tool_call_indexes: set[int],
) -> Iterator[LlmToolCallStarted | LlmToolCallDelta]:
    raw_calls = delta.get("tool_calls")
    if not isinstance(raw_calls, list):
        return
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        index = raw_call.get("index")
        if not isinstance(index, int):
            index = len(tool_call_parts)
        part = tool_call_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
        call_id = raw_call.get("id")
        if isinstance(call_id, str) and call_id:
            part["id"] = call_id
        function = raw_call.get("function")
        name_delta = ""
        arguments_delta = ""
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name:
                part["name"] += name
                name_delta = name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                part["arguments"] += arguments
                arguments_delta = arguments
        if index not in started_tool_call_indexes:
            started_tool_call_indexes.add(index)
            yield LlmToolCallStarted(index=index, call_id=part["id"], name=name_delta)
        if arguments_delta:
            yield LlmToolCallDelta(index=index, arguments_delta=arguments_delta)


def _parse_stream_tool_calls(tool_call_parts: dict[int, dict[str, str]]) -> list[LlmToolCall]:
    return [tool_call for _, tool_call in _parse_stream_tool_call_items(tool_call_parts)]


def _parse_stream_tool_call_items(tool_call_parts: dict[int, dict[str, str]]) -> list[tuple[int, LlmToolCall]]:
    calls: list[tuple[int, LlmToolCall]] = []
    for index in sorted(tool_call_parts):
        part = tool_call_parts[index]
        name = part.get("name", "")
        if not name:
            continue
        calls.append(
            (
                index,
                LlmToolCall(
                call_id=part.get("id") or name,
                name=name,
                arguments=_parse_arguments(part.get("arguments", "")),
                ),
            )
        )
    return calls


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


def _first_finish_reason(data: object) -> str | None:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices, list):
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    finish_reason = first.get("finish_reason")
    return finish_reason if isinstance(finish_reason, str) and finish_reason else None


def _usage(data: object) -> dict[str, object] | None:
    usage = data.get("usage") if isinstance(data, dict) else None
    return usage if isinstance(usage, dict) else None


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
