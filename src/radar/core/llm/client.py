from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from radar.core.config import RadarConfig
from radar.core.llm.anthropic_client import chat_anthropic
from radar.core.llm.openai_client import chat_openai

ChatMessage = dict[str, str]


class LlmConfigError(RuntimeError):
    """LLM 配置错误；调用方可转成 CLI/Web 友好的错误文案。"""


@dataclass(frozen=True)
class RuntimeLlmProvider:
    name: str
    protocol: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    max_tokens: int | None
    temperature: float | None
    headers: dict[str, str]


ChatImpl = Callable[
    [
        RuntimeLlmProvider,
        list[ChatMessage],
        str | None,
        float | None,
        int | None,
    ],
    str,
]


def resolve_provider(
    config: RadarConfig,
    *,
    provider_name: str | None = None,
    task: str | None = None,
) -> tuple[str, RuntimeLlmProvider]:
    """解析任务路由和敏感配置，返回一次请求可直接使用的 provider。"""

    if not config.llm.providers:
        raise LlmConfigError("未配置 LLM provider")

    selected_name = provider_name
    if selected_name is None and task:
        selected_name = config.llm.task_routing.get(task)
    if selected_name is None:
        selected_name = config.llm.default_provider or next(iter(config.llm.providers))

    provider = config.llm.providers.get(selected_name)
    if provider is None:
        available = ", ".join(config.llm.providers) or "(无)"
        raise LlmConfigError(f"LLM provider 不存在: {selected_name}，可用: {available}")

    secret = config.secrets.llm.get(provider.secret_ref)
    if secret is None:
        raise LlmConfigError(f"未配置 LLM secret: {provider.secret_ref}")

    runtime = RuntimeLlmProvider(
        name=selected_name,
        protocol=provider.protocol,
        base_url=secret.base_url,
        api_key=secret.api_key,
        model=provider.model,
        timeout=provider.timeout,
        max_tokens=provider.max_tokens,
        temperature=provider.temperature,
        headers=provider.headers,
    )
    return selected_name, runtime


def chat(
    config: RadarConfig,
    messages: list[ChatMessage],
    *,
    provider_name: str | None = None,
    task: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """发送 LLM 聊天请求；业务层负责控制 prompt 和成本。"""

    _, provider = resolve_provider(config, provider_name=provider_name, task=task)
    return _chat_impl(provider)(provider, messages, model, temperature, max_tokens)


def chat_json(
    config: RadarConfig,
    messages: list[ChatMessage],
    *,
    provider_name: str | None = None,
    task: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    """发送请求并解析 JSON object；失败时补一轮纠错提示。"""

    for attempt in range(2):
        raw = chat(config, messages, provider_name=provider_name, task=task, model=model).strip()
        try:
            parsed = json.loads(_strip_json_fence(raw))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            if attempt == 0:
                messages = _retry_json_messages(messages, raw, "object")
                continue
            raise
    return {}


def chat_json_list(
    config: RadarConfig,
    messages: list[ChatMessage],
    *,
    provider_name: str | None = None,
    task: str | None = None,
    model: str | None = None,
) -> list[dict[str, object]]:
    """发送请求并解析 JSON array；dict 会兼容包装成单元素数组。"""

    for attempt in range(2):
        raw = chat(config, messages, provider_name=provider_name, task=task, model=model).strip()
        try:
            parsed = json.loads(_strip_json_fence(raw))
            if isinstance(parsed, list):
                return cast(list[dict[str, object]], parsed)
            if isinstance(parsed, dict):
                return [cast(dict[str, object], parsed)]
            return []
        except json.JSONDecodeError:
            if attempt == 0:
                messages = _retry_json_messages(messages, raw, "array")
                continue
            raise
    return []


def _chat_impl(provider: RuntimeLlmProvider) -> ChatImpl:
    if provider.protocol == "anthropic":
        return chat_anthropic
    return chat_openai


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) <= 2:
        return text
    return "\n".join(lines[1:-1]).strip()


def _retry_json_messages(
    messages: list[ChatMessage],
    raw: str,
    expected: str,
) -> list[ChatMessage]:
    if expected == "array":
        instruction = "返回格式不是合法 JSON 数组，请重新输出纯 JSON 数组，不要包含 markdown 代码块。"
    else:
        instruction = "返回格式不是合法 JSON 对象，请重新输出纯 JSON 对象，不要包含 markdown 代码块。"
    return messages + [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": instruction},
    ]
