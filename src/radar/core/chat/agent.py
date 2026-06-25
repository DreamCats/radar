from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from radar.core.chat.builtin_extensions import RadarBuiltinExtension
from radar.core.chat.extensions import ChatExtension, build_tool_registry
from radar.core.chat.events import ChatEvent, ChatEventType, ChatMessage, new_id, now_iso
from radar.core.chat.prompts import DEFAULT_CHAT_SYSTEM_PROMPT
from radar.core.chat.skill_tools import build_skill_tools
from radar.core.chat.skills import ChatSkillLibrary, ChatSkillSelection
from radar.core.chat.store import ChatSessionStore
from radar.core.chat.tools import ToolRegistry
from radar.core.config import RadarConfig
from radar.core.llm import (
    LlmChatDone,
    LlmChatResponse,
    LlmReasoningDelta,
    LlmToolCall,
    LlmToolCallDelta,
    LlmToolCallDone,
    LlmToolCallStarted,
    chat_response,
    resolve_provider,
    stream_chat_response,
)


@dataclass(frozen=True)
class ChatTurnResult:
    session_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage
    tool_messages: list[ChatMessage]
    events: list[ChatEvent]


@dataclass(frozen=True)
class ChatTurnStreamEvent:
    type: str
    message: ChatMessage | None = None
    content: str | None = None
    event: ChatEvent | None = None


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
        self.skills = ChatSkillLibrary.from_config(config)
        base_tools = tools.list() if tools else []
        base_tools.extend(build_skill_tools(self.skills))
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
        llm_content: str | None = None,
        system_prompt: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_tool_rounds: int | None = None,
    ) -> ChatTurnResult:
        if not content.strip():
            raise ValueError("用户输入不能为空")

        events: list[ChatEvent] = []
        llm_metadata = self._llm_metadata(provider_name=provider_name, model=model)
        skill_selection = self._select_skills(llm_content or content)
        allowed_tool_names = None
        enabled_tools = self._enabled_tool_names(allowed_tool_names)
        user_message = ChatMessage(
            message_id=new_id(),
            role="user",
            content=content,
            created_at=now_iso(),
            metadata={"llm": llm_metadata, "skills": skill_selection.names},
        )
        self.store.append_message(session_id, user_message)

        turn_started = self._append_event(
            session_id,
            "turn_started",
            {
                "user_message_id": user_message.message_id,
                "active_skills": skill_selection.names,
                "enabled_tools": enabled_tools,
            },
        )
        events.append(turn_started)

        tool_messages: list[ChatMessage] = []
        try:
            tool_round = 0
            while True:
                if max_tool_rounds is not None and tool_round > max_tool_rounds:
                    raise RuntimeError(f"工具调用超过最大轮数: {max_tool_rounds}")
                response = self._request_llm(
                    session_id,
                    content_overrides={user_message.message_id: llm_content} if llm_content else None,
                    system_prompt=system_prompt,
                    skill_selection=skill_selection,
                    allowed_tool_names=allowed_tool_names,
                    provider_name=provider_name,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if not response.tool_calls:
                    assistant_message = self._append_assistant_message(
                        session_id,
                        response,
                        llm_metadata=llm_metadata,
                    )
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

                self._append_assistant_message(
                    session_id,
                    response,
                    llm_metadata=llm_metadata,
                )
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
                    tool_message = self._execute_tool_call(session_id, tool_call, allowed_tool_names=allowed_tool_names)
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
                tool_round += 1
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

    def stream_turn(
        self,
        session_id: str,
        content: str,
        *,
        llm_content: str | None = None,
        system_prompt: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_tool_rounds: int | None = None,
    ) -> Iterator[ChatTurnStreamEvent]:
        if not content.strip():
            raise ValueError("用户输入不能为空")

        llm_metadata = self._llm_metadata(provider_name=provider_name, model=model)
        skill_selection = self._select_skills(llm_content or content)
        allowed_tool_names = None
        enabled_tools = self._enabled_tool_names(allowed_tool_names)
        user_message = ChatMessage(
            message_id=new_id(),
            role="user",
            content=content,
            created_at=now_iso(),
            metadata={"llm": llm_metadata, "skills": skill_selection.names},
        )
        self.store.append_message(session_id, user_message)
        yield ChatTurnStreamEvent(type="user_message", message=user_message)

        turn_started = self._append_event(
            session_id,
            "turn_started",
            {
                "user_message_id": user_message.message_id,
                "active_skills": skill_selection.names,
                "enabled_tools": enabled_tools,
            },
        )
        yield ChatTurnStreamEvent(type="event", event=turn_started)

        tool_messages: list[ChatMessage] = []
        try:
            tool_round = 0
            while True:
                if max_tool_rounds is not None and tool_round > max_tool_rounds:
                    raise RuntimeError(f"工具调用超过最大轮数: {max_tool_rounds}")
                response: LlmChatResponse | None = None
                candidate_chunks: list[str] = []
                tool_stream_started = False
                for stream_event in self._request_llm_stream(
                    session_id,
                    content_overrides={user_message.message_id: llm_content} if llm_content else None,
                    system_prompt=system_prompt,
                    skill_selection=skill_selection,
                    allowed_tool_names=allowed_tool_names,
                    provider_name=provider_name,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    if isinstance(stream_event, LlmChatDone):
                        response = stream_event.response
                    elif isinstance(stream_event, LlmReasoningDelta):
                        yield ChatTurnStreamEvent(type="assistant_reasoning_delta", content=stream_event.content)
                    elif isinstance(stream_event, (LlmToolCallStarted, LlmToolCallDelta, LlmToolCallDone)):
                        if not tool_stream_started:
                            tool_stream_started = True
                            candidate_content = "".join(candidate_chunks)
                            candidate_chunks.clear()
                            if candidate_content:
                                yield ChatTurnStreamEvent(type="assistant_candidate_discard", content=candidate_content)
                    elif stream_event.content:
                        if tool_stream_started:
                            yield ChatTurnStreamEvent(type="assistant_progress_delta", content=stream_event.content)
                        else:
                            candidate_chunks.append(stream_event.content)
                            yield ChatTurnStreamEvent(type="assistant_candidate_delta", content=stream_event.content)
                if response is None:
                    response = LlmChatResponse(content="", tool_calls=[])
                candidate_content = "".join(candidate_chunks)
                confirmed_content = response.content or candidate_content
                if confirmed_content and (candidate_content or not tool_stream_started):
                    yield ChatTurnStreamEvent(
                        type="assistant_candidate_discard" if tool_stream_started or response.tool_calls else "assistant_candidate_commit",
                        content=confirmed_content,
                    )

                assistant_message = self._append_assistant_message(
                    session_id,
                    response,
                    llm_metadata=llm_metadata,
                )
                yield ChatTurnStreamEvent(type="assistant_message", message=assistant_message)
                if not response.tool_calls:
                    completed = self._append_event(
                        session_id,
                        "turn_completed",
                        {
                            "user_message_id": user_message.message_id,
                            "assistant_message_id": assistant_message.message_id,
                            "tool_count": len(tool_messages),
                        },
                    )
                    yield ChatTurnStreamEvent(type="event", event=completed)
                    return

                for tool_call in response.tool_calls:
                    started = self._append_event(
                        session_id,
                        "tool_execution_started",
                        {
                            "tool_call_id": tool_call.call_id,
                            "tool_name": tool_call.name,
                        },
                    )
                    yield ChatTurnStreamEvent(type="event", event=started)
                    tool_message = self._execute_tool_call(session_id, tool_call, allowed_tool_names=allowed_tool_names)
                    tool_messages.append(tool_message)
                    yield ChatTurnStreamEvent(type="tool_message", message=tool_message)
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
                    yield ChatTurnStreamEvent(type="event", event=completed)
                tool_round += 1
        except Exception as error:
            failed = self._append_event(
                session_id,
                "turn_failed",
                {
                    "user_message_id": user_message.message_id,
                    "error": str(error)[:1000],
                },
            )
            yield ChatTurnStreamEvent(type="event", event=failed)
            raise

    def _request_llm(
        self,
        session_id: str,
        *,
        content_overrides: dict[str, str] | None = None,
        system_prompt: str | None,
        skill_selection: ChatSkillSelection,
        allowed_tool_names: set[str] | None,
        provider_name: str | None,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> LlmChatResponse:
        return chat_response(
            self.config,
            self._build_llm_messages(
                session_id,
                system_prompt,
                skill_prompt=self.skills.render_catalog_prompt(),
                content_overrides=content_overrides,
            ),
            provider_name=provider_name,
            task="chat",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._llm_tool_specs(allowed_tool_names),
            enable_thinking=True,
        )

    def _request_llm_stream(
        self,
        session_id: str,
        *,
        content_overrides: dict[str, str] | None = None,
        system_prompt: str | None,
        skill_selection: ChatSkillSelection,
        allowed_tool_names: set[str] | None,
        provider_name: str | None,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ):
        yield from stream_chat_response(
            self.config,
            self._build_llm_messages(
                session_id,
                system_prompt,
                skill_prompt=self.skills.render_catalog_prompt(),
                content_overrides=content_overrides,
            ),
            provider_name=provider_name,
            task="chat",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._llm_tool_specs(allowed_tool_names),
            enable_thinking=True,
        )

    def _append_assistant_message(
        self,
        session_id: str,
        response: LlmChatResponse,
        *,
        llm_metadata: dict[str, Any],
    ) -> ChatMessage:
        metadata: dict[str, Any] = {
            "tool_calls": [asdict(call) for call in response.tool_calls],
            "llm": llm_metadata,
        }
        assistant_message = ChatMessage(
            message_id=new_id(),
            role="assistant",
            content=response.content,
            created_at=now_iso(),
            metadata=metadata,
        )
        self.store.append_message(session_id, assistant_message)
        return assistant_message

    def _llm_metadata(self, *, provider_name: str | None, model: str | None) -> dict[str, Any]:
        metadata: dict[str, Any] = {"thinking_enabled": True}
        if self.config.llm.providers:
            selected_name, provider = resolve_provider(self.config, provider_name=provider_name, task="chat")
            metadata.update(
                {
                    "provider_name": selected_name,
                    "protocol": provider.protocol,
                    "model": model or provider.model,
                }
            )
            return metadata
        if provider_name:
            metadata["provider_name"] = provider_name
        if model:
            metadata["model"] = model
        return metadata

    def _execute_tool_call(
        self,
        session_id: str,
        tool_call: LlmToolCall,
        *,
        allowed_tool_names: set[str] | None,
    ) -> ChatMessage:
        tool = self.tools.get(tool_call.name)
        is_error = False
        if tool is None:
            is_error = True
            result = {"error": f"未知工具: {tool_call.name}"}
        elif allowed_tool_names is not None and tool_call.name not in allowed_tool_names:
            is_error = True
            result = {"error": f"工具未被当前 skill 开放: {tool_call.name}"}
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

    def _build_llm_messages(
        self,
        session_id: str,
        system_prompt: str | None,
        *,
        skill_prompt: str = "",
        content_overrides: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        resolved_system_prompt = system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT
        if resolved_system_prompt:
            resolved_system_prompt = f"{resolved_system_prompt}\n\n当日日期：{_today_prompt_date()}"
        if skill_prompt:
            resolved_system_prompt = f"{resolved_system_prompt}\n\n{skill_prompt}" if resolved_system_prompt else skill_prompt
        if resolved_system_prompt:
            messages.append({"role": "system", "content": resolved_system_prompt})
        for message in self.store.load_messages(session_id):
            if message.role in {"system", "user", "assistant"}:
                content = content_overrides.get(message.message_id, message.content) if content_overrides else message.content
                if content:
                    messages.append({"role": message.role, "content": content})
            elif message.role == "tool":
                tool_name = message.metadata.get("tool_name", "unknown")
                messages.append({"role": "user", "content": f"工具 {tool_name} 返回：{message.content}"})
        return messages

    def _select_skills(self, text: str) -> ChatSkillSelection:
        return self.skills.select(text, max_active=self.config.chat.skills.max_active)

    def _enabled_tool_names(self, allowed_tool_names: set[str] | None) -> list[str]:
        return [tool.name for tool in self.tools.list(read_only=True) if allowed_tool_names is None or tool.name in allowed_tool_names]

    def _llm_tool_specs(self, allowed_tool_names: set[str] | None):
        return [
            tool.to_llm_spec()
            for tool in self.tools.list(read_only=True)
            if allowed_tool_names is None or tool.name in allowed_tool_names
        ]

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


def _today_prompt_date() -> str:
    return date.today().isoformat()
