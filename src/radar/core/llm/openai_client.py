from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from radar.core.llm.client import ChatMessage, RuntimeLlmProvider


def chat_openai(
    provider: "RuntimeLlmProvider",
    messages: list["ChatMessage"],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """OpenAI Chat Completions 协议，兼容大多数 OpenAI-like 网关。"""

    payload: dict[str, object] = {
        "model": model or provider.model,
        "messages": messages,
    }
    effective_temperature = temperature if temperature is not None else provider.temperature
    if effective_temperature is not None:
        payload["temperature"] = effective_temperature
    effective_max_tokens = max_tokens or provider.max_tokens
    if effective_max_tokens:
        payload["max_tokens"] = effective_max_tokens

    with httpx.Client(timeout=provider.timeout) as client:
        response = client.post(
            _chat_completions_url(provider.base_url),
            headers=_headers(provider),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices, list):
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


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
