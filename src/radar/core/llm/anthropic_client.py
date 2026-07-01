from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING
from urllib.parse import urlparse

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


def chat_anthropic(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
) -> str:
    """Anthropic Messages 协议；system 会提升到独立字段。"""

    return chat_anthropic_response(
        provider,
        messages,
        model,
        temperature,
        max_tokens,
        disable_thinking,
    ).content


def chat_anthropic_response(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
    tools: list["LlmToolSpec"] | None = None,
    enable_thinking: bool = False,
) -> LlmChatResponse:
    """Anthropic Messages 响应，包含文本和 tool calls。"""

    with httpx.Client(timeout=provider.timeout) as client:
        response = client.post(
            f"{_normalize_base_url(provider.base_url)}/v1/messages",
            headers=_headers(provider),
            json=_payload(provider, messages, model, temperature, max_tokens, disable_thinking, tools, enable_thinking),
        )
        response.raise_for_status()
        data = response.json()

    blocks = data.get("content") if isinstance(data, dict) else None
    if not isinstance(blocks, list):
        return LlmChatResponse(
            content="",
            tool_calls=[],
            stop_reason=_optional_text(data.get("stop_reason")) if isinstance(data, dict) else None,
            usage=_optional_dict(data.get("usage")) if isinstance(data, dict) else None,
        )

    parts: list[str] = []
    tool_calls: list[LlmToolCall] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            if isinstance(name, str) and name:
                raw_input = block.get("input")
                tool_calls.append(
                    LlmToolCall(
                        call_id=str(block.get("id") or name),
                        name=name,
                        arguments=raw_input if isinstance(raw_input, dict) else {},
                    )
                )
    return LlmChatResponse(
        content="".join(parts),
        tool_calls=tool_calls,
        stop_reason=_optional_text(data.get("stop_reason")) if isinstance(data, dict) else None,
        usage=_optional_dict(data.get("usage")) if isinstance(data, dict) else None,
    )


def stream_chat_anthropic_response(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
    tools: list["LlmToolSpec"] | None = None,
    enable_thinking: bool = False,
) -> Iterator[LlmChatStreamEvent]:
    """Anthropic Messages SSE，边返回文本边聚合最终 tool calls。"""

    payload = _payload(provider, messages, model, temperature, max_tokens, disable_thinking, tools, enable_thinking)
    payload["stream"] = True
    content_parts: list[str] = []
    tool_call_parts: dict[int, dict[str, str]] = {}
    stop_reason: str | None = None
    usage: dict[str, object] | None = None

    with httpx.Client(timeout=provider.timeout) as client:
        with client.stream(
            "POST",
            f"{_normalize_base_url(provider.base_url)}/v1/messages",
            headers={**_headers(provider), "Accept": "text/event-stream"},
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                data = _parse_stream_line(line)
                if data is None:
                    continue
                event_type = data.get("type")
                if event_type == "content_block_start":
                    started = _collect_tool_block_start(tool_call_parts, data)
                    if started is not None:
                        yield started
                elif event_type == "content_block_delta":
                    content, reasoning, tool_delta = _collect_content_delta(tool_call_parts, data)
                    if reasoning:
                        yield LlmReasoningDelta(content=reasoning)
                    if content:
                        content_parts.append(content)
                        yield LlmChatDelta(content=content)
                    if tool_delta is not None:
                        yield tool_delta
                elif event_type == "message_delta":
                    stop_reason = _stream_stop_reason(data) or stop_reason
                    usage = _stream_usage(data) or usage
                elif event_type == "message_stop":
                    break

    tool_call_items = _parse_stream_tool_call_items(tool_call_parts)
    for index, tool_call in tool_call_items:
        yield LlmToolCallDone(index=index, tool_call=tool_call)

    yield LlmChatDone(
        response=LlmChatResponse(
            content="".join(content_parts),
            tool_calls=[tool_call for _, tool_call in tool_call_items],
            stop_reason=stop_reason,
            usage=usage,
        )
    )


def _parse_stream_line(line: str) -> dict | None:
    text = line.strip()
    if not text or text.startswith(":") or not text.startswith("data:"):
        return None
    try:
        data = json.loads(text.removeprefix("data:").strip())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _collect_tool_block_start(tool_call_parts: dict[int, dict[str, str]], data: dict) -> LlmToolCallStarted | None:
    index = data.get("index")
    block = data.get("content_block")
    if not isinstance(index, int) or not isinstance(block, dict) or block.get("type") != "tool_use":
        return None
    name = block.get("name")
    if not isinstance(name, str) or not name:
        return None
    call_id = str(block.get("id") or name)
    tool_call_parts[index] = {
        "id": call_id,
        "name": name,
        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False, separators=(",", ":")),
    }
    return LlmToolCallStarted(index=index, call_id=call_id, name=name)


def _collect_content_delta(
    tool_call_parts: dict[int, dict[str, str]], data: dict
) -> tuple[str, str, LlmToolCallDelta | None]:
    delta = data.get("delta")
    if not isinstance(delta, dict):
        return "", "", None
    if delta.get("type") == "text_delta":
        text = delta.get("text")
        return text if isinstance(text, str) else "", "", None
    if delta.get("type") in {"thinking_delta", "reasoning_delta"}:
        thinking = delta.get("thinking") or delta.get("reasoning") or delta.get("text")
        return "", thinking if isinstance(thinking, str) else "", None
    if delta.get("type") == "input_json_delta":
        index = data.get("index")
        partial = delta.get("partial_json")
        if isinstance(index, int) and isinstance(partial, str):
            part = tool_call_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if part["arguments"] == "{}":
                part["arguments"] = ""
            part["arguments"] += partial
            return "", "", LlmToolCallDelta(index=index, arguments_delta=partial)
    return "", "", None


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
                arguments=_parse_tool_input(part.get("arguments", "")),
                ),
            )
        )
    return calls


def _parse_tool_input(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stream_stop_reason(data: dict) -> str | None:
    delta = data.get("delta")
    if not isinstance(delta, dict):
        return None
    return _optional_text(delta.get("stop_reason"))


def _stream_usage(data: dict) -> dict[str, object] | None:
    return _optional_dict(data.get("usage"))


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _payload(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    disable_thinking: bool,
    tools: list["LlmToolSpec"] | None = None,
    enable_thinking: bool = False,
) -> dict[str, object]:
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            anthropic_messages.append({"role": role, "content": content})
        else:
            anthropic_messages.append({"role": "user", "content": content})

    payload: dict[str, object] = {
        "model": model or provider.model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens or provider.max_tokens or 8192,
    }
    effective_temperature = temperature if temperature is not None else provider.temperature
    if effective_temperature is not None:
        payload["temperature"] = effective_temperature
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    elif enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}
        payload["temperature"] = 1
        if int(payload["max_tokens"]) <= 1024:
            payload["max_tokens"] = 4096
    if tools:
        payload["tools"] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]
    return payload


def _headers(provider: "RuntimeLlmProvider") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Anthropic-Version": "2023-06-01",
        **provider.headers,
    }
    hostname = urlparse(provider.base_url).hostname or ""
    if hostname.lower() == "api.anthropic.com":
        headers["X-Api-Key"] = provider.api_key
    else:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    return headers


def _normalize_base_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    return trimmed[:-3] if trimmed.endswith("/v1") else trimmed
