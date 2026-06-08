from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from radar.core.chat.builtin_extensions import RadarBuiltinExtension
from radar.core.config import RadarConfig
from radar.core.chat.extensions import ChatExtension, build_tool_registry
from radar.core.chat.events import ChatEvent, ChatEventType, ChatMessage, new_id, now_iso
from radar.core.chat.prompts import DEFAULT_CHAT_SYSTEM_PROMPT
from radar.core.chat.store import ChatSessionStore
from radar.core.chat.tools import ToolRegistry
from radar.core.llm import LlmChatResponse, LlmToolCall, chat_response


@dataclass(frozen=True)
class ChatTurnResult:
    session_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage
    tool_messages: list[ChatMessage]
    events: list[ChatEvent]


class ChatAgent:
    """Core chat runner with file-backed persistence.

    只负责底层对话、tool loop 和文件持久化；Web/API 只应消费这层能力。
    """

    def __init__(
        self,
        config: RadarConfig,
        *,
        store: ChatSessionStore | None = None,
        tools: ToolRegistry | None = None,
        extensions: list[ChatExtension] | None = None,
        enable_builtin_tools: bool = True,
    ):
        self.config = config
        self.store = store or ChatSessionStore.from_config(config)
        base_tools = tools.list() if tools else None
        all_extensions = list(extensions or [])
        if enable_builtin_tools:
            all_extensions.append(RadarBuiltinExtension(config))
        self.tools = build_tool_registry(tools=base_tools, extensions=all_extensions)

    def create_session(
        self,
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        return self.store.create_session(title=title, metadata=metadata)

    def run_turn(
        self,
        session_id: str,
        content: str,
        *,
        system_prompt: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_tool_rounds: int = 4,
    ) -> ChatTurnResult:
        if not content.strip():
            raise ValueError("用户输入不能为空")

        events: list[ChatEvent] = []
        user_message = ChatMessage(
            message_id=new_id(),
            role="user",
            content=content,
            created_at=now_iso(),
        )
        self.store.append_message(session_id, user_message)

        turn_started = self._append_event(
            session_id,
            "turn_started",
            {
                "user_message_id": user_message.message_id,
                "enabled_tools": [tool.name for tool in self.tools.list(read_only=True)],
            },
        )
        events.append(turn_started)

        tool_messages: list[ChatMessage] = []
        try:
            for _round in range(max_tool_rounds + 1):
                response = self._request_llm(
                    session_id,
                    system_prompt=system_prompt,
                    provider_name=provider_name,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if not response.tool_calls:
                    assistant_message = self._append_assistant_message(session_id, response)
                    completed = self._append_event(
                        session_id,
                        "turn_completed",
                        {
                            "user_message_id": user_message.message_id,
                            "assistant_message_id": assistant_message.message_id,
                            "tool_count": len(tool_messages),
                        },
                    )
                    events.append(completed)
                    return ChatTurnResult(
                        session_id=session_id,
                        user_message=user_message,
                        assistant_message=assistant_message,
                        tool_messages=tool_messages,
                        events=events,
                    )

                self._append_assistant_message(session_id, response)
                for tool_call in response.tool_calls:
                    started = self._append_event(
                        session_id,
                        "tool_execution_started",
                        {
                            "tool_call_id": tool_call.call_id,
                            "tool_name": tool_call.name,
                        },
                    )
                    events.append(started)
                    tool_message = self._execute_tool_call(session_id, tool_call)
                    tool_messages.append(tool_message)
                    completed = self._append_event(
                        session_id,
                        "tool_execution_completed",
                        {
                            "tool_call_id": tool_call.call_id,
                            "tool_name": tool_call.name,
                            "tool_message_id": tool_message.message_id,
                            "is_error": bool(tool_message.metadata.get("is_error")),
                        },
                    )
                    events.append(completed)
            raise RuntimeError(f"工具调用超过最大轮数: {max_tool_rounds}")
        except Exception as error:
            failed = self._append_event(
                session_id,
                "turn_failed",
                {
                    "user_message_id": user_message.message_id,
                    "error": str(error)[:1000],
                },
            )
            events.append(failed)
            raise

    def _request_llm(
        self,
        session_id: str,
        *,
        system_prompt: str | None,
        provider_name: str | None,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> LlmChatResponse:
        return chat_response(
            self.config,
            self._build_llm_messages(session_id, system_prompt),
            provider_name=provider_name,
            task="chat",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self.tools.to_llm_specs(read_only=True),
        )

    def _append_assistant_message(self, session_id: str, response: LlmChatResponse) -> ChatMessage:
        assistant_message = ChatMessage(
            message_id=new_id(),
            role="assistant",
            content=response.content,
            created_at=now_iso(),
            metadata={"tool_calls": [asdict(call) for call in response.tool_calls]},
        )
        self.store.append_message(session_id, assistant_message)
        return assistant_message

    def _execute_tool_call(self, session_id: str, tool_call: LlmToolCall) -> ChatMessage:
        tool = self.tools.get(tool_call.name)
        is_error = False
        if tool is None:
            is_error = True
            result = {"error": f"未知工具: {tool_call.name}"}
        elif not tool.read_only:
            is_error = True
            result = {"error": f"工具未开放给 LLM: {tool_call.name}"}
        else:
            try:
                result = tool.execute(tool_call.arguments)
            except Exception as error:
                is_error = True
                result = {"error": str(error)[:1000]}

        tool_message = ChatMessage(
            message_id=new_id(),
            role="tool",
            content=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            created_at=now_iso(),
            metadata={
                "tool_call_id": tool_call.call_id,
                "tool_name": tool_call.name,
                "is_error": is_error,
            },
        )
        self.store.append_message(session_id, tool_message)
        return tool_message

    def _build_llm_messages(self, session_id: str, system_prompt: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        resolved_system_prompt = system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT
        if resolved_system_prompt:
            messages.append({"role": "system", "content": resolved_system_prompt})
        for message in self.store.load_messages(session_id):
            if message.role in {"system", "user", "assistant"}:
                if message.content:
                    messages.append({"role": message.role, "content": message.content})
            elif message.role == "tool":
                tool_name = message.metadata.get("tool_name", "unknown")
                messages.append({"role": "user", "content": f"工具 {tool_name} 返回：{message.content}"})
        return messages

    def _append_event(self, session_id: str, event_type: ChatEventType, payload: dict[str, Any]) -> ChatEvent:
        event = ChatEvent(
            event_id=new_id(),
            session_id=session_id,
            type=event_type,
            created_at=now_iso(),
            payload=payload,
        )
        self.store.append_event(event)
        return event
