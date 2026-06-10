"""File-backed AI chat primitives used by CLI and future Web surfaces."""

from radar.core.chat.agent import ChatAgent, ChatTurnResult, ChatTurnStreamEvent
from radar.core.chat.builtin_extensions import RadarBuiltinExtension
from radar.core.chat.events import ChatEvent, ChatEventType, ChatMessage, ChatRole, ChatSession
from radar.core.chat.extensions import ChatExtension, ExtensionContext, build_tool_registry
from radar.core.chat.prompts import COMMON_CHAT_SYSTEM_PROMPT, DEFAULT_CHAT_SYSTEM_PROMPT, SURFACE_PROMPTS, build_chat_system_prompt
from radar.core.chat.skills import ChatSkill, ChatSkillLibrary, ChatSkillSelection, load_chat_skills, parse_chat_skill
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
    "ChatSkill",
    "ChatSkillLibrary",
    "ChatSkillSelection",
    "COMMON_CHAT_SYSTEM_PROMPT",
    "DEFAULT_CHAT_SYSTEM_PROMPT",
    "RadarBuiltinExtension",
    "ChatSessionStore",
    "ChatTool",
    "ChatTurnResult",
    "ChatTurnStreamEvent",
    "ExtensionContext",
    "ToolRegistry",
    "SURFACE_PROMPTS",
    "build_tool_registry",
    "build_chat_system_prompt",
    "load_chat_skills",
    "parse_chat_skill",
]
