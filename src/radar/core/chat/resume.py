from __future__ import annotations

from typing import Any

from radar.core.chat.agent import ChatTurnStreamEvent
from radar.core.chat.events import ChatEvent, ChatMessage
from radar.core.llm import LlmChatDone, LlmChatResponse, LlmReasoningDelta


def can_continue_chat_session(events: list[ChatEvent]) -> bool:
    latest_started_index = _latest_event_index(events, "turn_started")
    if latest_started_index is None:
        return False
    later_events = events[latest_started_index + 1 :]
    if any(event.type in {"turn_completed", "turn_failed"} for event in later_events):
        return False
    return True


def stream_continue_turn(
    agent: Any,
    session_id: str,
    *,
    provider_name: str | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    max_tool_rounds: int | None = None,
):
    agent.store.get_session(session_id)
    user_message = _latest_user_message(agent.store.load_messages(session_id))
    if user_message is None:
        raise ValueError("没有可继续的用户消息")
    if not can_continue_chat_session(agent.store.load_events(session_id)):
        raise ValueError("当前会话没有可继续的中断生成")

    llm_metadata = agent._llm_metadata(provider_name=provider_name, model=model)
    allowed_tool_names = None
    started = agent._append_event(
        session_id,
        "turn_started",
        {
            "user_message_id": user_message.message_id,
            "resumed": True,
            "enabled_tools": agent._enabled_tool_names(allowed_tool_names),
        },
    )
    yield ChatTurnStreamEvent(type="event", event=started)

    tool_messages: list[ChatMessage] = []
    try:
        tool_round = 0
        while True:
            if max_tool_rounds is not None and tool_round > max_tool_rounds:
                raise RuntimeError(f"工具调用超过最大轮数: {max_tool_rounds}")
            response: LlmChatResponse | None = None
            for stream_event in agent._request_llm_stream(
                session_id,
                content_overrides=None,
                system_prompt=system_prompt,
                skill_selection=agent._select_skills(user_message.content),
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
                elif stream_event.content:
                    yield ChatTurnStreamEvent(type="assistant_delta", content=stream_event.content)
            if response is None:
                response = LlmChatResponse(content="", tool_calls=[])

            assistant_message = agent._append_assistant_message(
                session_id,
                response,
                llm_metadata=llm_metadata,
                user_content=user_message.content,
            )
            yield ChatTurnStreamEvent(type="assistant_message", message=assistant_message)
            if not response.tool_calls:
                completed = agent._append_event(
                    session_id,
                    "turn_completed",
                    {
                        "user_message_id": user_message.message_id,
                        "assistant_message_id": assistant_message.message_id,
                        "tool_count": len(tool_messages),
                        "resumed": True,
                    },
                )
                yield ChatTurnStreamEvent(type="event", event=completed)
                return

            for tool_call in response.tool_calls:
                started = agent._append_event(
                    session_id,
                    "tool_execution_started",
                    {"tool_call_id": tool_call.call_id, "tool_name": tool_call.name},
                )
                yield ChatTurnStreamEvent(type="event", event=started)
                tool_message = agent._execute_tool_call(session_id, tool_call, allowed_tool_names=allowed_tool_names)
                tool_messages.append(tool_message)
                yield ChatTurnStreamEvent(type="tool_message", message=tool_message)
                completed = agent._append_event(
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
        failed = agent._append_event(
            session_id,
            "turn_failed",
            {"user_message_id": user_message.message_id, "error": str(error)[:1000], "resumed": True},
        )
        yield ChatTurnStreamEvent(type="event", event=failed)
        raise


def _latest_event_index(events: list[ChatEvent], event_type: str) -> int | None:
    for index in range(len(events) - 1, -1, -1):
        if events[index].type == event_type:
            return index
    return None


def _latest_user_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for message in reversed(messages):
        if message.role == "user":
            return message
    return None
