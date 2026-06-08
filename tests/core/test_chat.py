from __future__ import annotations

from datetime import datetime

from radar.core.chat import ChatAgent, ChatMessage, ChatSessionStore, ChatTool, ExtensionContext, ToolRegistry
from radar.core.chat.events import new_id, now_iso
from radar.core.config import RadarConfig
from radar.core.llm import LlmChatResponse, LlmToolCall
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages


def test_chat_session_store_appends_events_and_messages(tmp_path):
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session(title="测试对话", metadata={"source": "unit"})

    store.append_message(
        session.session_id,
        ChatMessage(message_id=new_id(), role="user", content="你好", created_at=now_iso()),
    )

    events = store.load_events(session.session_id)
    messages = store.load_messages(session.session_id)

    assert session.session_id
    assert [item.role for item in messages] == ["user"]
    assert messages[0].content == "你好"
    assert [event.type for event in events] == ["session_created", "message_appended"]
    assert (tmp_path / "chat" / "sessions" / session.session_id / "events.jsonl").exists()


def test_chat_agent_passes_file_backed_context_to_llm(tmp_path, monkeypatch):
    config = RadarConfig()
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    seen = {}

    def fake_chat_response(config, messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return LlmChatResponse(content="收到", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    agent = ChatAgent(config, store=store)
    result = agent.run_turn(
        session.session_id,
        "帮我看一下今天消息",
        system_prompt="你是 radar 投研助手",
        provider_name="openai_main",
    )

    assert result.assistant_message.content == "收到"
    assert seen["messages"] == [
        {"role": "system", "content": "你是 radar 投研助手"},
        {"role": "user", "content": "帮我看一下今天消息"},
    ]
    assert seen["kwargs"]["task"] == "chat"
    assert seen["kwargs"]["provider_name"] == "openai_main"
    assert seen["kwargs"]["tools"]


def test_chat_agent_executes_extension_tool_and_continues(tmp_path, monkeypatch):
    config = RadarConfig()
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    class SearchExtension:
        name = "search"

        def register(self, context: ExtensionContext) -> None:
            context.register_tool(
                ChatTool(
                    name="search_messages",
                    description="搜索本地消息",
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    handler=lambda args: {"items": [f"命中:{args['query']}"]},
                )
            )

    def fake_chat_response(config, messages, **kwargs):
        calls.append({"messages": messages, "tools": kwargs["tools"]})
        if len(calls) == 1:
            return LlmChatResponse(
                content="",
                tool_calls=[
                    LlmToolCall(
                        call_id="call-1",
                        name="search_messages",
                        arguments={"query": "AI"},
                    )
                ],
            )
        return LlmChatResponse(content="找到 1 条", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    agent = ChatAgent(config, store=store, extensions=[SearchExtension()])
    result = agent.run_turn(session.session_id, "查一下 AI")

    messages = store.load_messages(session.session_id)
    events = store.load_events(session.session_id)

    assert result.assistant_message.content == "找到 1 条"
    assert [message.role for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2].metadata["tool_name"] == "search_messages"
    assert messages[2].content == '{"items":["命中:AI"]}'
    assert "工具 search_messages 返回" in calls[1]["messages"][-1]["content"]
    assert calls[0]["tools"][0].name == "search_messages"
    assert "tool_execution_started" in [event.type for event in events]
    assert "tool_execution_completed" in [event.type for event in events]


def test_tool_registry_keeps_read_only_contract():
    registry = ToolRegistry()
    registry.register(
        ChatTool(
            name="search_messages",
            description="搜索本地消息",
            input_schema={"type": "object"},
            handler=lambda args: {"query": args["query"]},
        )
    )

    assert registry.get("search_messages").execute({"query": "AI"}) == {"query": "AI"}
    assert [tool.name for tool in registry.list(read_only=True)] == ["search_messages"]


def test_chat_agent_registers_builtin_radar_tools(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path})
    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    tool_names = [tool.name for tool in agent.tools.list(read_only=True)]

    assert "radar_search_messages" in tool_names
    assert "radar_get_stock_price_history" in tool_names
    assert "radar_backtest_summary" in tool_names


def test_builtin_message_tools_read_local_database(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path})
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-04T09:00:00", "东财策略", "AI 算力"),
                _message("m2", "2026-06-04T09:02:00", "东财策略", "AI 继续发酵"),
                _message("m3", "2026-06-04T09:03:00", "其他群", "固态电池"),
            ],
        )
    finally:
        conn.close()

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    search_result = agent.tools.get("radar_search_messages").execute({"keyword": "AI", "limit": 5})
    context_result = agent.tools.get("radar_get_message_context").execute({"message_id": "m2", "radius": 2})
    conversations_result = agent.tools.get("radar_list_conversations").execute({"limit": 5})

    assert [item["message_id"] for item in search_result["items"]] == ["m2", "m1"]
    assert context_result["target"]["message_id"] == "m2"
    assert [item["message_id"] for item in context_result["before"]] == ["m1"]
    assert [item["title"] for item in conversations_result["items"]] == ["其他群", "东财策略"]


def test_builtin_tushare_tool_is_whitelisted(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    monkeypatch.setattr("radar.core.chat.builtin_extensions.resolve_stock", lambda config, value: "600519.SH")

    def fake_tushare_call(config, api_name, params, fields):
        captured.update({"api_name": api_name, "params": params, "fields": fields})
        return [{"ts_code": "600519.SH", "trade_date": "20260603", "close": 100.0}]

    monkeypatch.setattr("radar.core.chat.builtin_extensions.tushare_call", fake_tushare_call)

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    result = agent.tools.get("radar_get_stock_price_history").execute(
        {"stock": "贵州茅台", "api_name": "daily", "start_date": "20260601", "end_date": "20260603"}
    )

    assert result["ts_code"] == "600519.SH"
    assert captured["api_name"] == "daily"
    assert captured["params"] == {"ts_code": "600519.SH", "start_date": "20260601", "end_date": "20260603"}
    assert "close" in captured["fields"]


def test_chat_agent_records_unknown_tool_as_error(tmp_path, monkeypatch):
    config = RadarConfig()
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    def fake_chat_response(config, messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return LlmChatResponse(
                content="",
                tool_calls=[LlmToolCall(call_id="call-missing", name="missing_tool", arguments={})],
            )
        return LlmChatResponse(content="工具不可用", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store).run_turn(session.session_id, "调用不存在的工具")

    tool_message = store.load_messages(session.session_id)[2]
    assert result.assistant_message.content == "工具不可用"
    assert tool_message.role == "tool"
    assert tool_message.metadata["is_error"] is True
    assert "未知工具" in tool_message.content


def _message(message_id: str, message_time: str, group_name: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        fetch_window="20260604090000-20260604100000",
    )
