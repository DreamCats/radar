from __future__ import annotations

from datetime import datetime

from radar.core.chat import (
    DEFAULT_CHAT_SYSTEM_PROMPT,
    ChatAgent,
    ChatMessage,
    ChatSessionStore,
    ChatTool,
    ExtensionContext,
    ToolRegistry,
)
from radar.core.chat.events import new_id, now_iso
from radar.core.config import RadarConfig
from radar.core.llm import LlmChatDelta, LlmChatDone, LlmChatResponse, LlmReasoningDelta, LlmToolCall
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages
from radar.core.tushare import RealtimeDailyQuote


class CountingSearchExtension:
    name = "search"

    def register(self, context: ExtensionContext) -> None:
        context.register_tool(
            ChatTool(
                name="search_messages",
                description="搜索本地消息",
                input_schema={"type": "object"},
                handler=lambda args: {"round": args["round"]},
            )
        )


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


def test_chat_session_store_lists_sessions(tmp_path):
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session(title="测试对话")

    sessions = store.list_sessions()

    assert [item.session_id for item in sessions] == [session.session_id]


def test_chat_session_store_deletes_session_directory(tmp_path):
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session(title="待删除")

    store.delete_session(session.session_id)

    assert not store.session_dir(session.session_id).exists()
    assert store.list_sessions() == []


def test_chat_session_store_reads_unicode_line_separator(tmp_path):
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    content = "涨价\u2028Q3/Q4 可能继续验证"

    store.append_message(
        session.session_id,
        ChatMessage(message_id=new_id(), role="tool", content=content, created_at=now_iso()),
    )

    events = store.load_events(session.session_id)
    messages = store.load_messages(session.session_id)

    assert len(events) == 2
    assert messages[0].content == content


def test_chat_agent_passes_file_backed_context_to_llm(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    seen = {}

    def fake_chat_response(config, messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return LlmChatResponse(content="收到", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)
    monkeypatch.setattr("radar.core.chat.agent._today_prompt_date", lambda: "2026-06-09")

    agent = ChatAgent(config, store=store)
    result = agent.run_turn(
        session.session_id,
        "帮我看一下今天消息",
        system_prompt="你是 radar 投研助手",
        provider_name="openai_main",
    )

    assert result.assistant_message.content == "收到"
    assert result.user_message.metadata["llm"]["provider_name"] == "openai_main"
    assert result.assistant_message.metadata["llm"]["provider_name"] == "openai_main"
    assert seen["messages"] == [
        {"role": "system", "content": "你是 radar 投研助手\n\n当日日期：2026-06-09"},
        {"role": "user", "content": "帮我看一下今天消息"},
    ]
    assert seen["kwargs"]["task"] == "chat"
    assert seen["kwargs"]["provider_name"] == "openai_main"
    assert seen["kwargs"]["tools"]


def test_chat_agent_records_resolved_llm_metadata(tmp_path, monkeypatch):
    config = RadarConfig(
        llm={"providers": {"deep": {"protocol": "anthropic", "secret_ref": "deep-secret", "model": "claude-test"}}},
        secrets={"llm": {"deep-secret": {"base_url": "https://llm.invalid", "api_key": "key"}}},
    )
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()

    def fake_chat_response(config, messages, **kwargs):
        return LlmChatResponse(content="收到", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store).run_turn(session.session_id, "你好", provider_name="deep")

    assert result.user_message.metadata["llm"] == {
        "thinking_enabled": True,
        "provider_name": "deep",
        "protocol": "anthropic",
        "model": "claude-test",
    }
    assert result.assistant_message.metadata["llm"]["provider_name"] == "deep"


def test_chat_agent_can_send_context_to_llm_without_persisting_it(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    seen = {}

    def fake_chat_response(config, messages, **kwargs):
        seen["messages"] = messages
        return LlmChatResponse(content="收到", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    ChatAgent(config, store=store).run_turn(session.session_id, "你好", llm_content="你好\n\n页面上下文：\n{}")

    messages = store.load_messages(session.session_id)
    assert messages[0].content == "你好"
    assert seen["messages"][1] == {"role": "user", "content": "你好\n\n页面上下文：\n{}"}


def test_chat_agent_uses_default_system_prompt(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    seen = {}

    def fake_chat_response(config, messages, **kwargs):
        seen["messages"] = messages
        return LlmChatResponse(content="收到", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)
    monkeypatch.setattr("radar.core.chat.agent._today_prompt_date", lambda: "2026-06-09")

    ChatAgent(config, store=store).run_turn(session.session_id, "今天有什么机会？")

    assert seen["messages"][0] == {"role": "system", "content": f"{DEFAULT_CHAT_SYSTEM_PROMPT}\n\n当日日期：2026-06-09"}
    assert seen["messages"][1] == {"role": "user", "content": "今天有什么机会？"}


def test_chat_agent_streams_and_persists_final_message(tmp_path, monkeypatch):
    config = RadarConfig()
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()

    def fake_stream_chat_response(config, messages, **kwargs):
        assert kwargs["enable_thinking"] is True
        assert messages[1] == {"role": "user", "content": "这个信号怎么看？\n\n页面上下文：\n{}"}
        yield LlmReasoningDelta(content="需要先看上下文。")
        yield LlmChatDelta(content="先")
        yield LlmChatDelta(content="看")
        yield LlmChatDone(response=LlmChatResponse(content="先看", tool_calls=[]))

    monkeypatch.setattr("radar.core.chat.agent.stream_chat_response", fake_stream_chat_response)

    events = list(
        ChatAgent(config, store=store).stream_turn(
            session.session_id,
            "这个信号怎么看？",
            llm_content="这个信号怎么看？\n\n页面上下文：\n{}",
        )
    )
    messages = store.load_messages(session.session_id)

    assert [event.content for event in events if event.type == "assistant_reasoning_delta"] == ["需要先看上下文。"]
    assert [event.content for event in events if event.type == "assistant_delta"] == ["先", "看"]
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "这个信号怎么看？"
    assert messages[-1].content == "先看"


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
    assert "search_messages" in {tool.name for tool in calls[0]["tools"]}
    assert "tool_execution_started" in [event.type for event in events]
    assert "tool_execution_completed" in [event.type for event in events]


def test_chat_agent_allows_unlimited_tool_rounds_by_default(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    def fake_chat_response(config, messages, **kwargs):
        calls.append(messages)
        if len(calls) <= 7:
            return LlmChatResponse(
                content="",
                tool_calls=[
                    LlmToolCall(
                        call_id=f"call-{len(calls)}",
                        name="search_messages",
                        arguments={"round": len(calls)},
                    )
                ],
            )
        return LlmChatResponse(content="完成", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store, extensions=[CountingSearchExtension()], enable_builtin_tools=False).run_turn(
        session.session_id,
        "连续查",
    )

    assert result.assistant_message.content == "完成"
    assert len(result.tool_messages) == 7
    assert len(calls) == 8


def test_chat_agent_stream_allows_unlimited_tool_rounds_by_default(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    def fake_stream_chat_response(config, messages, **kwargs):
        calls.append(messages)
        if len(calls) <= 7:
            yield LlmChatDone(
                response=LlmChatResponse(
                    content="",
                    tool_calls=[
                        LlmToolCall(
                            call_id=f"call-{len(calls)}",
                            name="search_messages",
                            arguments={"round": len(calls)},
                        )
                    ],
                )
            )
            return
        yield LlmChatDone(response=LlmChatResponse(content="完成", tool_calls=[]))

    monkeypatch.setattr("radar.core.chat.agent.stream_chat_response", fake_stream_chat_response)

    events = list(
        ChatAgent(config, store=store, extensions=[CountingSearchExtension()], enable_builtin_tools=False).stream_turn(
            session.session_id,
            "连续查",
        )
    )

    assert [event.message.content for event in events if event.type == "assistant_message"][-1] == "完成"
    assert len([event for event in events if event.type == "tool_message"]) == 7
    assert len(calls) == 8


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
    assert "radar_get_realtime_daily_quote" in tool_names
    assert "radar_get_stock_moneyflow" in tool_names
    assert "radar_get_stock_technical_factors" in tool_names
    assert "radar_get_limit_pool" in tool_names
    assert "radar_backtest_summary" in tool_names
    assert "radar_source_signals" not in tool_names


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

    monkeypatch.setattr("radar.core.chat.tushare_tools.resolve_stock", lambda config, value: "600519.SH")

    def fake_tushare_call(config, api_name, params, fields):
        captured.update({"api_name": api_name, "params": params, "fields": fields})
        return [{"ts_code": "600519.SH", "trade_date": "20260603", "close": 100.0}]

    monkeypatch.setattr("radar.core.chat.tushare_tools.tushare_call", fake_tushare_call)

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    result = agent.tools.get("radar_get_stock_price_history").execute(
        {"stock": "贵州茅台", "api_name": "daily", "start_date": "20260601", "end_date": "20260603"}
    )

    assert result["ts_code"] == "600519.SH"
    assert captured["api_name"] == "daily"
    assert captured["params"] == {"ts_code": "600519.SH", "start_date": "20260601", "end_date": "20260603"}
    assert "close" in captured["fields"]


def test_builtin_realtime_daily_quote_tool_uses_rt_k_helper(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    monkeypatch.setattr("radar.core.chat.tushare_tools.resolve_stock", lambda config, value: "300503.SZ")

    def fake_realtime_quote(config, *, ts_code, use_cache):
        captured.update({"ts_code": ts_code, "use_cache": use_cache})
        return RealtimeDailyQuote(
            ts_code="300503.SZ",
            name="昊志机电",
            pre_close=87.01,
            open=83.5,
            high=85.68,
            low=82.51,
            close=84.75,
            vol=16575961,
            amount=1395413519.46,
            num=47447,
        )

    monkeypatch.setattr("radar.core.chat.tushare_tools.get_realtime_daily_quote", fake_realtime_quote)

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    result = agent.tools.get("radar_get_realtime_daily_quote").execute({"stock": "300503.SZ", "use_cache": False})

    assert result["found"] is True
    assert result["ts_code"] == "300503.SZ"
    assert result["name"] == "昊志机电"
    assert result["open"] == 83.5
    assert result["close"] == 84.75
    assert captured == {"ts_code": "300503.SZ", "use_cache": False}


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
