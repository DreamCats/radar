"""File-backed AI chat primitives used by CLI and future Web surfaces."""

from radar.core.chat.agent import ChatAgent, ChatTurnResult
from radar.core.chat.builtin_extensions import RadarBuiltinExtension
from radar.core.chat.events import ChatEvent, ChatEventType, ChatMessage, ChatRole, ChatSession
from radar.core.chat.extensions import ChatExtension, ExtensionContext, build_tool_registry
from radar.core.chat.store import ChatSessionStore
from radar.core.chat.tools import ChatTool, ToolRegistry

__all__ = [
    "ChatAgent",
    "ChatEvent",
    "ChatEventType",
    "ChatMessage",
    "ChatRole",
    "ChatSession",
    "ChatExtension",
    "RadarBuiltinExtension",
    "ChatSessionStore",
    "ChatTool",
    "ChatTurnResult",
    "ExtensionContext",
    "ToolRegistry",
    "build_tool_registry",
]
