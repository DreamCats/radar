from __future__ import annotations

from fastapi.testclient import TestClient

from radar.core.chat import ChatSessionStore
from radar.core.config import RadarConfig
from radar.web.server.app import create_app


def test_chat_session_delete_endpoint_removes_file_backed_session(tmp_path):
    config = RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        }
    )
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="待删除")

    client = TestClient(create_app(config))
    response = client.delete(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 204
    assert not store.session_dir(session.session_id).exists()
    assert client.get(f"/api/chat/sessions/{session.session_id}").status_code == 404


def test_chat_session_detail_folds_intermediate_assistant_messages_into_trace(tmp_path):
    from radar.core.chat import ChatEvent, ChatMessage
    from radar.core.chat.events import new_id

    config = RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        }
    )
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="微信会话")
    user_message = ChatMessage(
        message_id=new_id(),
        role="user",
        content="从微信消息里找高频主题",
        created_at="2026-06-08T10:00:00",
    )
    intermediate_message = ChatMessage(
        message_id=new_id(),
        role="assistant",
        content="我来获取最热门股票的行情数据。",
        created_at="2026-06-08T10:00:01",
        metadata={
            "tool_calls": [
                {
                    "call_id": "call_price",
                    "name": "radar_get_stock_price_history",
                    "arguments": {"stock": "002371.SZ"},
                }
            ]
        },
    )
    tool_message = ChatMessage(
        message_id=new_id(),
        role="tool",
        content='{"items":[{"ts_code":"002371.SZ"}]}',
        created_at="2026-06-08T10:00:02",
        metadata={
            "tool_call_id": "call_price",
            "tool_name": "radar_get_stock_price_history",
        },
    )
    final_message = ChatMessage(
        message_id=new_id(),
        role="assistant",
        content="最终结论：半导体设备反复出现。",
        created_at="2026-06-08T10:00:03",
    )

    store.append_message(session.session_id, user_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_started",
            created_at="2026-06-08T10:00:00",
            payload={"user_message_id": user_message.message_id},
        )
    )
    store.append_message(session.session_id, intermediate_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="tool_execution_started",
            created_at="2026-06-08T10:00:01.100000",
            payload={"tool_call_id": "call_price", "tool_name": "radar_get_stock_price_history"},
        )
    )
    store.append_message(session.session_id, tool_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="tool_execution_completed",
            created_at="2026-06-08T10:00:02",
            payload={
                "tool_call_id": "call_price",
                "tool_name": "radar_get_stock_price_history",
                "tool_message_id": tool_message.message_id,
            },
        )
    )
    store.append_message(session.session_id, final_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_completed",
            created_at="2026-06-08T10:00:03",
            payload={
                "user_message_id": user_message.message_id,
                "assistant_message_id": final_message.message_id,
            },
        )
    )

    client = TestClient(create_app(config))
    response = client.get(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert data["session"]["message_count"] == 2
    assert [message["content"] for message in messages] == [
        "从微信消息里找高频主题",
        "最终结论：半导体设备反复出现。",
    ]
    assistant_metadata = messages[1]["metadata"]
    assert assistant_metadata["duration_ms"] == 3000
    assert assistant_metadata["tool_activities"] == [
        {"key": "call_price", "label": "行情数据", "status": "completed", "toolMessageId": tool_message.message_id}
    ]
    trace_items = assistant_metadata["trace_items"]
    assert {
        "key": "status-3",
        "type": "status",
        "label": "我来获取最热门股票的行情数据。",
    } in trace_items
    assert {
        "key": "tool-call_price",
        "type": "tool",
        "toolCallId": "call_price",
        "toolMessageId": tool_message.message_id,
        "label": "行情数据",
        "status": "completed",
    } in trace_items
    assert trace_items[-1]["type"] == "assistant"
    assert trace_items[-1]["content"] == "最终结论：半导体设备反复出现。"

    tool_response = client.get(f"/api/chat/sessions/{session.session_id}/tool-messages/{tool_message.message_id}")

    assert tool_response.status_code == 200
    assert tool_response.json()["content"] == '{"items":[{"ts_code":"002371.SZ"}]}'
