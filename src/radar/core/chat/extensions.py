from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from radar.core.chat.tools import ChatTool, ToolRegistry


@dataclass(frozen=True)
class ExtensionContext:
    tools: ToolRegistry

    def register_tool(self, tool: ChatTool) -> None:
        self.tools.register(tool)


class ChatExtension(Protocol):
    """Native Python extension that can register chat capabilities."""

    name: str

    def register(self, context: ExtensionContext) -> None:
        ...


def build_tool_registry(
    *,
    tools: list[ChatTool] | None = None,
    extensions: list[ChatExtension] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(tools)
    context = ExtensionContext(tools=registry)
    for extension in extensions or []:
        extension.register(context)
    return registry
