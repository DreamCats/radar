from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from radar.core.chat import (
    ChatAgent,
    ChatEvent,
    ChatMessage,
    ChatRun,
    ChatRunStore,
    ChatSession,
    ChatSessionStore,
    build_chat_system_prompt,
)
from radar.core.chat.resume import can_continue_chat_session, stream_continue_turn
from radar.core.config import RadarConfig
from radar.web.server.chat_display import build_chat_display_messages
from radar.web.server.chat_run_worker import (
    ensure_chat_run_worker,
    sse,
    start_chat_run_worker,
    stream_chat_run_events,
    stream_item_sse,
)
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    ChatContinueRequest,
    ChatActiveRunResponse,
    ChatModelOptionResponse,
    ChatModelOptionsResponse,
    ChatMessageResponse,
    ChatRunResponse,
    ChatRunStartResponse,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatTurnRequest,
    ChatTurnResponse,
)

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/model-options", response_model=ChatModelOptionsResponse)
def chat_model_options(config: RadarConfig = Depends(get_config)) -> ChatModelOptionsResponse:
    default_provider_name = _default_chat_provider_name(config)
    items = [
        ChatModelOptionResponse(
            provider_name=name,
            label=_provider_label(name, provider.model, is_default=name == default_provider_name),
            protocol=provider.protocol,
            model=provider.model,
            context_window_tokens=provider.context_window_tokens,
            is_default=name == default_provider_name,
        )
        for name, provider in config.llm.providers.items()
    ]
    return ChatModelOptionsResponse(default_provider_name=default_provider_name, items=items)


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
def chat_sessions(config: RadarConfig = Depends(get_config), limit: int = 50) -> ChatSessionListResponse:
    store = ChatSessionStore.from_config(config)
    items: list[ChatSessionResponse] = []
    for session in store.list_sessions():
        messages = store.load_messages(session.session_id)
        events = store.load_events(session.session_id)
        display_messages = build_chat_display_messages(messages, events)
        items.append(_session_response(session, display_messages, events=events))
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return ChatSessionListResponse(items=items[: max(1, min(limit, 100))])


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse)
def chat_session_detail(session_id: str, config: RadarConfig = Depends(get_config)) -> ChatSessionDetailResponse:
    store = ChatSessionStore.from_config(config)
    try:
        session = store.get_session(session_id)
        messages = store.load_messages(session_id)
        events = store.load_events(session_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    assistant_durations = _assistant_turn_durations(events)
    display_messages = build_chat_display_messages(messages, events)
    return ChatSessionDetailResponse(
        session=_session_response(session, display_messages, events=events),
        messages=[
            _message_response(message, duration_ms=assistant_durations.get(message.message_id))
            for message in display_messages
            if _visible_message(message)
        ],
    )


@router.get("/chat/sessions/{session_id}/tool-messages/{message_id}", response_model=ChatMessageResponse)
def chat_tool_message_detail(
    session_id: str,
    message_id: str,
    config: RadarConfig = Depends(get_config),
) -> ChatMessageResponse:
    store = ChatSessionStore.from_config(config)
    try:
        for message in store.load_messages(session_id):
            if message.message_id == message_id and message.role == "tool":
                return ChatMessageResponse(**message.model_dump())
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    raise HTTPException(status_code=404, detail="工具结果不存在")


@router.delete("/chat/sessions/{session_id}", status_code=204)
def delete_chat_session(session_id: str, config: RadarConfig = Depends(get_config)) -> None:
    store = ChatSessionStore.from_config(config)
    try:
        store.delete_session(session_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/chat/turn", response_model=ChatTurnResponse)
def chat_turn(
    request: ChatTurnRequest,
    config: RadarConfig = Depends(get_config),
) -> ChatTurnResponse:
    agent = ChatAgent(config)
    try:
        session_id = request.session_id
        if not session_id:
            session = agent.create_session(title=request.title, metadata=request.metadata)
            session_id = session.session_id
        result = agent.run_turn(
            session_id,
            request.content,
            llm_content=_content_with_context(request.content, request.context),
            system_prompt=build_chat_system_prompt(_surface_from_context(request.context)),
            provider_name=request.provider_name,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)[:1000]) from error

    assistant_durations = _assistant_turn_durations(getattr(result, "events", []))
    return ChatTurnResponse(
        session_id=result.session_id,
        user_message=ChatMessageResponse(**result.user_message.model_dump()),
        assistant_message=_message_response(
            result.assistant_message,
            duration_ms=assistant_durations.get(result.assistant_message.message_id),
        ),
        tool_messages=[ChatMessageResponse(**message.model_dump()) for message in result.tool_messages],
    )


@router.post("/chat/turn/stream")
def chat_turn_stream(
    request: ChatTurnRequest,
    config: RadarConfig = Depends(get_config),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_turn(request, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/sessions/{session_id}/continue/stream")
def chat_continue_stream(
    session_id: str,
    request: ChatContinueRequest,
    config: RadarConfig = Depends(get_config),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_continue(session_id, request, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/runs", response_model=ChatRunStartResponse)
def create_chat_run(
    request: ChatTurnRequest,
    config: RadarConfig = Depends(get_config),
) -> ChatRunStartResponse:
    agent = ChatAgent(config)
    run_store = ChatRunStore.from_config(config)
    try:
        session_id = request.session_id
        if not session_id:
            session = agent.create_session(title=request.title, metadata=request.metadata)
            session_id = session.session_id
        else:
            agent.store.get_session(session_id)
        run = run_store.create_run(
            session_id,
            metadata=_run_metadata(request),
            request=_run_request(request),
        )
        run_store.append_event(run.run_id, "session", {"session_id": session_id})
        start_chat_run_worker(run.run_id, config)
        run = run_store.get_run(run.run_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)[:1000]) from error
    return ChatRunStartResponse(run=_chat_run_response(run))


@router.get("/chat/runs/active", response_model=ChatActiveRunResponse)
def active_chat_run(
    session_id: str | None = None,
    surface: str | None = None,
    entity_id: str | None = None,
    config: RadarConfig = Depends(get_config),
) -> ChatActiveRunResponse:
    try:
        run = ChatRunStore.from_config(config).active_run(
            session_id=session_id,
            surface=surface,
            entity_id=entity_id,
        )
        if run:
            ensure_chat_run_worker(run.run_id, config)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ChatActiveRunResponse(run=_chat_run_response(run) if run else None)


@router.get("/chat/runs/{run_id}/stream")
def chat_run_stream(
    run_id: str,
    after_seq: int = Query(default=0, ge=0),
    config: RadarConfig = Depends(get_config),
) -> StreamingResponse:
    store = ChatRunStore.from_config(config)
    try:
        store.get_run(run_id)
        ensure_chat_run_worker(run_id, config)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StreamingResponse(
        stream_chat_run_events(run_id, after_seq, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/runs/{run_id}/cancel", response_model=ChatRunStartResponse)
def cancel_chat_run(
    run_id: str,
    config: RadarConfig = Depends(get_config),
) -> ChatRunStartResponse:
    store = ChatRunStore.from_config(config)
    try:
        run = store.request_cancel(run_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ChatRunStartResponse(run=_chat_run_response(run))


def _stream_chat_turn(request: ChatTurnRequest, config: RadarConfig) -> Iterator[str]:
    agent = ChatAgent(config)
    try:
        session_id = request.session_id
        if not session_id:
            session = agent.create_session(title=request.title, metadata=request.metadata)
            session_id = session.session_id
        yield sse("session", {"session_id": session_id})

        content = _content_with_context(request.content, request.context)
        for item in agent.stream_turn(
            session_id,
            request.content,
            llm_content=content,
            system_prompt=build_chat_system_prompt(_surface_from_context(request.context)),
            provider_name=request.provider_name,
        ):
            yield stream_item_sse(item)
    except FileNotFoundError as error:
        yield sse("error", {"message": str(error), "status_code": 404})
    except ValueError as error:
        yield sse("error", {"message": str(error), "status_code": 400})
    except Exception as error:
        yield sse("error", {"message": str(error)[:1000], "status_code": 500})


def _stream_chat_continue(session_id: str, request: ChatContinueRequest, config: RadarConfig) -> Iterator[str]:
    agent = ChatAgent(config)
    try:
        session = agent.store.get_session(session_id)
        yield sse("session", {"session_id": session_id})
        for item in stream_continue_turn(
            agent,
            session_id,
            provider_name=request.provider_name,
            system_prompt=build_chat_system_prompt(_surface_from_context(session.metadata)),
        ):
            yield stream_item_sse(item)
    except FileNotFoundError as error:
        yield sse("error", {"message": str(error), "status_code": 404})
    except ValueError as error:
        yield sse("error", {"message": str(error), "status_code": 400})
    except Exception as error:
        yield sse("error", {"message": str(error)[:1000], "status_code": 500})


def _default_chat_provider_name(config: RadarConfig) -> str | None:
    if not config.llm.providers:
        return None
    routed = config.llm.task_routing.get("chat")
    if routed in config.llm.providers:
        return routed
    if config.llm.default_provider in config.llm.providers:
        return config.llm.default_provider
    return next(iter(config.llm.providers))


def _provider_label(name: str, model: str, *, is_default: bool) -> str:
    if is_default:
        return f"默认 · {model}"
    return f"{name} · {model}"


def _session_response(session: ChatSession, messages: list[ChatMessage], *, events: list[ChatEvent] | None = None) -> ChatSessionResponse:
    visible_messages = [message for message in messages if _visible_message(message)]
    latest_message = visible_messages[-1] if visible_messages else None
    updated_at = latest_message.created_at if latest_message else session.created_at
    preview = _display_content(latest_message).replace("\n", " ")[:120] if latest_message else ""
    return ChatSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=updated_at,
        title=session.title,
        metadata=session.metadata,
        message_count=len(visible_messages),
        preview=preview,
        can_continue=can_continue_chat_session(events or []),
    )


def _chat_run_response(run: ChatRun) -> ChatRunResponse:
    return ChatRunResponse(**run.model_dump(exclude={"metadata", "request"}))


def _run_metadata(request: ChatTurnRequest) -> dict[str, Any]:
    metadata = dict(request.metadata)
    if request.title:
        metadata.setdefault("title", request.title)
    surface = request.context.get("surface")
    entity_id = request.context.get("entity_id")
    if isinstance(surface, str):
        metadata.setdefault("surface", surface)
    if isinstance(entity_id, str):
        metadata.setdefault("entity_id", entity_id)
    return metadata


def _run_request(request: ChatTurnRequest) -> dict[str, Any]:
    return {
        "content": request.content,
        "llm_content": _content_with_context(request.content, request.context),
        "system_prompt": build_chat_system_prompt(_surface_from_context(request.context)),
        "provider_name": request.provider_name,
    }


def _visible_message(message: ChatMessage) -> bool:
    return message.role != "tool" and bool(message.content.strip())


def _message_response(message: ChatMessage, *, duration_ms: int | None = None) -> ChatMessageResponse:
    response = ChatMessageResponse(**message.model_dump())
    response.content = _display_content(message)
    if duration_ms is not None and message.role == "assistant":
        response.metadata = {**response.metadata, "duration_ms": duration_ms}
    return response


def _display_content(message: ChatMessage) -> str:
    if message.role != "user":
        return message.content.strip()
    return _strip_context_for_display(message.content)


def _strip_context_for_display(content: str) -> str:
    marker = "\n\n页面上下文：\n"
    if marker not in content:
        return content.strip()
    return content.split(marker, 1)[0].strip()


def _assistant_turn_durations(events: list[ChatEvent]) -> dict[str, int]:
    durations: dict[str, int] = {}
    started_at: datetime | None = None
    for event in events:
        if event.type == "turn_started":
            started_at = _parse_event_time(event.created_at)
            continue
        if event.type != "turn_completed" or started_at is None:
            continue
        assistant_message_id = event.payload.get("assistant_message_id")
        completed_at = _parse_event_time(event.created_at)
        if not isinstance(assistant_message_id, str) or completed_at is None:
            continue
        try:
            duration_ms = round((completed_at - started_at).total_seconds() * 1000)
        except TypeError:
            continue
        durations[assistant_message_id] = max(0, duration_ms)
        started_at = None
    return durations


def _parse_event_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _content_with_context(content: str, context: dict[str, Any]) -> str:
    if not context:
        return content
    return (
        f"{content.strip()}\n\n"
        "页面上下文：\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def _surface_from_context(context: dict[str, Any]) -> str | None:
    surface = context.get("surface")
    return surface if isinstance(surface, str) else None
