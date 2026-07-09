from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

from radar.core.chat import ChatAgent, ChatMessage, ChatRunEvent, ChatRunLeaseLost, ChatRunStore
from radar.core.chat.resume import can_continue_chat_session, stream_continue_turn
from radar.core.config import RadarConfig
from radar.core.valuation import project_completed_valuation_run
from radar.web.server.schemas import ChatMessageResponse

_ACTIVE_WORKERS: set[str] = set()
_ACTIVE_WORKERS_LOCK = threading.RLock()
WORKER_ENSURE_INTERVAL_SECONDS = 5.0
STREAM_KEEPALIVE_INTERVAL_SECONDS = 10.0


def start_chat_run_worker(run_id: str, config: RadarConfig) -> None:
    with _ACTIVE_WORKERS_LOCK:
        if run_id in _ACTIVE_WORKERS:
            return
        _ACTIVE_WORKERS.add(run_id)
    owner = uuid4().hex
    thread = threading.Thread(
        target=_execute_chat_run_thread,
        kwargs={"run_id": run_id, "config": config, "owner": owner},
        name=f"radar-chat-run-{run_id[:8]}",
        daemon=True,
    )
    thread.start()


def ensure_chat_run_worker(run_id: str, config: RadarConfig) -> None:
    store = ChatRunStore.from_config(config)
    run = store.get_run(run_id)
    if run.status != "running" or run.cancel_requested:
        return
    start_chat_run_worker(run_id, config)


def stream_chat_run_events(run_id: str, after_seq: int, config: RadarConfig) -> Iterator[str]:
    ensure_chat_run_worker(run_id, config)
    store = ChatRunStore.from_config(config)
    last_seq = after_seq
    next_worker_check_at = time.monotonic() + WORKER_ENSURE_INTERVAL_SECONDS
    last_send_at = time.monotonic()
    while True:
        for event in store.load_events(run_id, after_seq=last_seq):
            last_seq = event.seq
            last_send_at = time.monotonic()
            yield run_event_sse(event)
        run = store.get_run(run_id)
        if run.status != "running" and last_seq >= run.last_seq:
            return
        now = time.monotonic()
        if run.status == "running" and now >= next_worker_check_at:
            ensure_chat_run_worker(run_id, config)
            next_worker_check_at = now + WORKER_ENSURE_INTERVAL_SECONDS
        if run.status == "running" and now - last_send_at >= STREAM_KEEPALIVE_INTERVAL_SECONDS:
            last_send_at = now
            yield sse("ping", {"run_id": run_id, "sequence_number": last_seq})
        time.sleep(0.25)


def stream_item_sse(item: Any) -> str:
    event_name, data = stream_item_event(item)
    return sse(event_name, data)


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _execute_chat_run_thread(*, run_id: str, config: RadarConfig, owner: str) -> None:
    try:
        _execute_chat_run(run_id=run_id, config=config, owner=owner)
    finally:
        with _ACTIVE_WORKERS_LOCK:
            _ACTIVE_WORKERS.discard(run_id)


def _execute_chat_run(*, run_id: str, config: RadarConfig, owner: str) -> None:
    store = ChatRunStore.from_config(config)
    claimed = False
    try:
        run = store.claim_run(run_id, owner)
        if run is None:
            return
        claimed = True
        agent = ChatAgent(config)
        stream = _stream_for_run(agent, run)
        if stream is None:
            return
        for item in stream:
            run = store.heartbeat(run_id, owner=owner)
            if run.cancel_requested:
                _close_stream(stream)
                store.append_event(run_id, "error", {"message": "已停止", "status_code": 499})
                store.mark_cancelled(run_id)
                return
            event_name, data = stream_item_event(item)
            store.append_event(run_id, event_name, data)
        run = store.heartbeat(run_id, owner=owner)
        if run.cancel_requested:
            store.append_event(run_id, "error", {"message": "已停止", "status_code": 499})
            store.mark_cancelled(run_id)
            return
        _mark_completed_and_project(store, run_id, config)
    except ChatRunLeaseLost:
        return
    except FileNotFoundError as error:
        _fail_chat_run(store, run_id, str(error), 404)
    except ValueError as error:
        _fail_chat_run(store, run_id, str(error), 400)
    except Exception as error:
        _fail_chat_run(store, run_id, str(error)[:1000], 500)
    finally:
        if claimed:
            try:
                store.release_lease(run_id, owner)
            except FileNotFoundError:
                return


def _stream_for_run(agent: ChatAgent, run: Any):
    provider_name = _optional_text(run.request.get("provider_name"))
    system_prompt = _optional_text(run.request.get("system_prompt"))
    session_events = agent.store.load_events(run.session_id)
    if run.last_seq > 1:
        run_events = ChatRunStore.from_config(agent.config).load_events(run.run_id)
        user_message_id = _run_user_message_id(run_events)
        if user_message_id is None:
            return _start_full_run(agent, run, provider_name, system_prompt)
        turn_state = _turn_state_for_user(session_events, user_message_id)
        if turn_state is None:
            ChatRunStore.from_config(agent.config).mark_failed(
                run.run_id,
                "服务重启前尚未进入推理，请重新发送",
            )
            return None
        if turn_state == "completed":
            _mark_completed_and_project(ChatRunStore.from_config(agent.config), run.run_id, agent.config)
            return None
        if turn_state == "failed":
            ChatRunStore.from_config(agent.config).mark_failed(run.run_id, "上次生成失败")
            return None
        if turn_state == "running" and can_continue_chat_session(session_events):
            return stream_continue_turn(
                agent,
                run.session_id,
                provider_name=provider_name,
                system_prompt=system_prompt,
            )
        ChatRunStore.from_config(agent.config).mark_failed(run.run_id, "当前会话已有后续对话")
        return None
    return _start_full_run(agent, run, provider_name, system_prompt)


def _start_full_run(
    agent: ChatAgent,
    run: Any,
    provider_name: str | None,
    system_prompt: str | None,
):
    content = _required_text(run.request, "content")
    llm_content = _required_text(run.request, "llm_content")
    return agent.stream_turn(
        run.session_id,
        content,
        llm_content=llm_content,
        system_prompt=system_prompt,
        provider_name=provider_name,
    )


def stream_item_event(item: Any) -> tuple[str, dict[str, Any]]:
    if item.message is not None:
        message = _stream_message_response(item.message).model_dump(mode="json")
        return item.type, {"message": message}
    if item.content:
        return item.type, {"content": item.content}
    if item.event is not None:
        return "agent_event", {"event": item.event.model_dump(mode="json")}
    return "agent_event", {"event": {"type": item.type}}


def run_event_sse(event: ChatRunEvent) -> str:
    data = {
        **event.data,
        "run_id": event.run_id,
        "session_id": event.session_id,
        "sequence_number": event.seq,
    }
    return sse(event.event, data)


def _stream_message_response(message: ChatMessage) -> ChatMessageResponse:
    if message.role == "tool":
        message = message.model_copy(
            update={
                "content": "",
                "metadata": {**message.metadata, "stream_content_omitted": True},
            }
        )
    return ChatMessageResponse(**message.model_dump())


def _fail_chat_run(store: ChatRunStore, run_id: str, message: str, status_code: int) -> None:
    try:
        store.append_event(run_id, "error", {"message": message, "status_code": status_code})
        store.mark_failed(run_id, message)
    except FileNotFoundError:
        return


def _mark_completed_and_project(store: ChatRunStore, run_id: str, config: RadarConfig) -> None:
    run = store.mark_completed(run_id)
    try:
        measurement = project_completed_valuation_run(config, run)
    except Exception as exc:
        store.append_event(run_id, "valuation_projection", {"status": "failed", "message": str(exc)[:1000]})
        return
    if measurement is None:
        return
    store.append_event(
        run_id,
        "valuation_projection",
        {
            "status": measurement.parse_status,
            "measurement_id": measurement.measurement_id,
            "positive_count": measurement.positive_count,
        },
    )


def _close_stream(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        close()


def _run_user_message_id(events: list[ChatRunEvent]) -> str | None:
    for event in events:
        if event.event != "user_message":
            continue
        message = event.data.get("message")
        if isinstance(message, dict) and isinstance(message.get("message_id"), str):
            return message["message_id"]
    return None


def _turn_state_for_user(events: list[Any], user_message_id: str) -> str | None:
    started_index = None
    for index, event in enumerate(events):
        if event.type != "turn_started":
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        if payload.get("user_message_id") == user_message_id:
            started_index = index
            break
    if started_index is None:
        return None
    for event in events[started_index + 1 :]:
        if event.type == "turn_completed":
            return "completed"
        if event.type == "turn_failed":
            return "failed"
    return "running"


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"chat run 缺少请求字段: {key}")
    return value


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
