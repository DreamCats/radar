"""LLM protocol clients shared by future CLI/Web use cases."""

from radar.core.llm.client import (
    ChatMessage,
    LlmConfigError,
    RuntimeLlmProvider,
    chat,
    chat_json,
    chat_json_list,
    resolve_provider,
)

__all__ = [
    "ChatMessage",
    "LlmConfigError",
    "RuntimeLlmProvider",
    "chat",
    "chat_json",
    "chat_json_list",
    "resolve_provider",
]
