from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from radar.core.llm import LlmToolSpec

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ChatTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    read_only: bool = True

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.handler(args)

    def to_llm_spec(self) -> LlmToolSpec:
        return LlmToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


class ToolRegistry:
    """Small in-process tool registry for the future chat agent loop."""

    def __init__(self, tools: list[ChatTool] | None = None):
        self._tools: dict[str, ChatTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ChatTool) -> None:
        if not tool.name:
            raise ValueError("tool name 不能为空")
        if tool.name in self._tools:
            raise ValueError(f"tool 已存在: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ChatTool | None:
        return self._tools.get(name)

    def list(self, *, read_only: bool | None = None) -> list[ChatTool]:
        tools = list(self._tools.values())
        if read_only is None:
            return tools
        return [tool for tool in tools if tool.read_only is read_only]

    def to_llm_specs(self, *, read_only: bool | None = True) -> list[LlmToolSpec]:
        return [tool.to_llm_spec() for tool in self.list(read_only=read_only)]
