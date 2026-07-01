from __future__ import annotations

from typing import Any

from radar.core.chat import ChatEvent, ChatMessage

_PROCESS_SUMMARY_START = "我会先拆解你的问题，确定需要查哪些证据。"
_PROCESS_SUMMARY_TOOL_RESULT = "工具结果开始返回，我会把新增数据并入判断。"

_TOOL_LABELS = {
    "radar_analyst_backtest_summary": "分析师回测摘要",
    "radar_get_message_context": "消息上下文",
    "radar_get_realtime_quote": "实时行情",
    "radar_get_stock_financials": "财务数据",
    "radar_get_stock_forecast_or_segments": "预告与主营",
    "radar_get_stock_price_history": "行情数据",
    "radar_get_catalyst_valuation_report": "估值线索报告",
    "radar_list_catalyst_terms": "催化词词库",
    "radar_list_conversations": "会话列表",
    "radar_message_overview": "消息总览",
    "radar_resolve_stock": "股票代码解析",
    "radar_scan_catalysts": "催化词扫描",
    "radar_search_stock_disclosures": "公告检索",
    "radar_search_messages": "消息搜索",
}


def build_chat_display_messages(
    messages: list[ChatMessage],
    events: list[ChatEvent],
) -> list[ChatMessage]:
    if not events:
        return messages

    hidden_message_ids: set[str] = set()
    metadata_updates: dict[str, dict[str, Any]] = {}
    messages_by_id = {message.message_id: message for message in messages}
    turn_items: list[dict[str, Any]] | None = None

    for event in events:
        if event.type == "turn_started":
            turn_items = [{"kind": "turn_started"}]
            continue
        if turn_items is None:
            continue
        if event.type == "message_appended":
            message = _message_from_event(event)
            if message is None:
                continue
            if message.role == "assistant":
                turn_items.append(
                    {
                        "kind": "assistant_message",
                        "message_id": message.message_id,
                        "content": message.content,
                    }
                )
            elif message.role == "tool":
                turn_items.append({"kind": "tool_message"})
            continue
        if event.type in {"tool_execution_started", "tool_execution_completed"}:
            turn_items.append(
                {
                    "kind": "tool_event",
                    "event_type": event.type,
                    "tool_call_id": _optional_str(event.payload.get("tool_call_id")),
                    "tool_name": _optional_str(event.payload.get("tool_name")),
                    "tool_message_id": _optional_str(event.payload.get("tool_message_id")),
                }
            )
            continue
        if event.type != "turn_completed":
            continue

        assistant_message_id = _optional_str(event.payload.get("assistant_message_id"))
        if assistant_message_id and assistant_message_id in messages_by_id:
            final_message = messages_by_id[assistant_message_id]
            update = _display_metadata_for_turn(turn_items, final_message)
            if update:
                metadata_updates[assistant_message_id] = update
            hidden_message_ids.update(
                item["message_id"]
                for item in turn_items
                if item.get("kind") == "assistant_message"
                and item.get("message_id") != assistant_message_id
            )
        turn_items = None

    display_messages: list[ChatMessage] = []
    for message in messages:
        if message.message_id in hidden_message_ids:
            continue
        update = metadata_updates.get(message.message_id)
        if update:
            display_messages.append(
                message.model_copy(update={"metadata": {**message.metadata, **update}})
            )
            continue
        display_messages.append(message)
    return display_messages


def _display_metadata_for_turn(
    items: list[dict[str, Any]],
    final_message: ChatMessage,
) -> dict[str, Any]:
    trace_items: list[dict[str, Any]] = []
    tool_activities: list[dict[str, Any]] = []
    tool_result_summary_added = False

    for item in items:
        kind = item.get("kind")
        if kind == "turn_started":
            trace_items = _append_status_trace(trace_items, "正在理解问题")
            trace_items = _append_summary_trace(trace_items, _PROCESS_SUMMARY_START)
            continue
        if kind == "assistant_message":
            if item.get("message_id") == final_message.message_id:
                continue
            content = _optional_str(item.get("content"))
            if content:
                trace_items = _append_status_trace(trace_items, content)
            continue
        if kind == "tool_message":
            if not tool_result_summary_added:
                trace_items = _append_summary_trace(trace_items, _PROCESS_SUMMARY_TOOL_RESULT)
                tool_result_summary_added = True
            continue
        if kind != "tool_event":
            continue

        event_type = _optional_str(item.get("event_type"))
        tool_call_id = _optional_str(item.get("tool_call_id"))
        tool_name = _optional_str(item.get("tool_name"))
        tool_message_id = _optional_str(item.get("tool_message_id"))
        if event_type == "tool_execution_started":
            trace_items = _append_summary_trace(trace_items, _summary_for_tool_phase(tool_name))
        trace_items = _update_tool_trace(trace_items, event_type, tool_call_id, tool_name, tool_message_id)
        tool_activities = _update_tool_activities(
            tool_activities,
            event_type,
            tool_call_id,
            tool_name,
            tool_message_id,
        )

    final_content = final_message.content.strip()
    if trace_items and final_content:
        trace_items = _append_assistant_trace(trace_items, final_content)
    if not trace_items and not tool_activities:
        return {}
    return {
        "status": "已处理",
        "trace_items": trace_items,
        "tool_activities": tool_activities,
    }


def _message_from_event(event: ChatEvent) -> ChatMessage | None:
    raw = event.payload.get("message")
    if not isinstance(raw, dict):
        return None
    return ChatMessage.model_validate(raw)


def _append_status_trace(items: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    label = label.strip()
    if not label:
        return items
    if items and items[-1].get("type") == "status" and items[-1].get("label") == label:
        return items
    return [*items, {"key": f"status-{len(items) + 1}", "type": "status", "label": label}]


def _append_summary_trace(items: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    content = content.strip()
    if not content:
        return items
    if any(item.get("type") == "summary" and item.get("content") == content for item in items):
        return items
    return [*items, {"key": f"summary-{len(items) + 1}", "type": "summary", "content": content}]


def _append_assistant_trace(items: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    content = content.strip()
    if not content:
        return items
    return [*items, {"key": f"assistant-{len(items) + 1}", "type": "assistant", "content": content}]


def _update_tool_trace(
    items: list[dict[str, Any]],
    event_type: str,
    tool_call_id: str,
    tool_name: str,
    tool_message_id: str = "",
) -> list[dict[str, Any]]:
    if (
        not tool_call_id
        or not tool_name
        or event_type not in {"tool_execution_started", "tool_execution_completed"}
    ):
        return items
    status = "running" if event_type == "tool_execution_started" else "completed"
    for index, item in enumerate(items):
        if item.get("type") == "tool" and item.get("toolCallId") == tool_call_id:
            next_items = [*items]
            next_items[index] = {
                **item,
                "label": _format_tool_name(tool_name),
                "status": status,
                **({"toolMessageId": tool_message_id} if tool_message_id else {}),
            }
            return next_items
    return [
        *items,
        {
            "key": f"tool-{tool_call_id}",
            "type": "tool",
            "toolCallId": tool_call_id,
            "label": _format_tool_name(tool_name),
            "status": status,
            **({"toolMessageId": tool_message_id} if tool_message_id else {}),
        },
    ]


def _update_tool_activities(
    items: list[dict[str, Any]],
    event_type: str,
    tool_call_id: str,
    tool_name: str,
    tool_message_id: str = "",
) -> list[dict[str, Any]]:
    if (
        not tool_call_id
        or not tool_name
        or event_type not in {"tool_execution_started", "tool_execution_completed"}
    ):
        return items
    activity = {
        "key": tool_call_id,
        "label": _format_tool_name(tool_name),
        "status": "running" if event_type == "tool_execution_started" else "completed",
        **({"toolMessageId": tool_message_id} if tool_message_id else {}),
    }
    for index, item in enumerate(items):
        if item.get("key") == tool_call_id:
            next_items = [*items]
            next_items[index] = activity
            return next_items
    return [*items, activity]


def _format_tool_name(tool_name: str) -> str:
    return _TOOL_LABELS.get(tool_name, tool_name or "工具")


def _summary_for_tool_phase(tool_name: str) -> str:
    normalized = tool_name.lower()
    if _contains_any(
        normalized,
        ["strategy", "candidate", "theme", "dashboard", "策略", "候选", "主题"],
    ):
        return "我会先用现有消息、行情和外部来源补齐可比证据。"
    if _contains_any(normalized, ["evidence", "证据"]):
        return "我会补原文证据、验证点和暂缓条件。"
    if _contains_any(
        normalized,
        ["message", "conversation", "context", "overview", "消息", "会话", "上下文"],
    ):
        return "我会回到本地消息里补原文证据、来源密度和反证。"
    if _contains_any(
        normalized,
        [
            "stock",
            "price",
            "market",
            "sector",
            "moneyflow",
            "limit",
            "backtest",
            "行情",
            "资金",
            "板块",
            "涨停",
            "回测",
        ],
    ):
        return "我会补行情和资金流，确认市场是否已经定价。"
    if _contains_any(normalized, ["skill", "load", "模板", "技能"]):
        return "我会补必要的分析模板，再把结果整理成结论。"
    return "我会补齐下一步判断需要的数据。"


def _contains_any(value: str, needles: list[str]) -> bool:
    return any(needle in value for needle in needles)


def _optional_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
