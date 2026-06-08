"""LLM protocol clients shared by future CLI/Web use cases."""

from radar.core.llm.client import (
    ChatMessage,
    LlmChatResponse,
    LlmConfigError,
    LlmToolCall,
    LlmToolSpec,
    RuntimeLlmProvider,
    chat,
    chat_json,
    chat_json_list,
    chat_response,
    resolve_provider,
)

__all__ = [
    "ChatMessage",
    "LlmChatResponse",
    "LlmConfigError",
    "LlmToolCall",
    "LlmToolSpec",
    "RuntimeLlmProvider",
    "chat",
    "chat_json",
    "chat_json_list",
    "chat_response",
    "resolve_provider",
]
