from __future__ import annotations

from datetime import datetime

from radar.core.chat import (
    COMMON_CHAT_SYSTEM_PROMPT,
    DEFAULT_CHAT_SYSTEM_PROMPT,
    ChatAgent,
    ChatEvent,
    ChatMessage,
    ChatRunLeaseLost,
    ChatRunStore,
    ChatSessionStore,
    ChatTool,
    ExtensionContext,
    ToolRegistry,
    build_chat_system_prompt,
)
from radar.core.chat.resume import can_continue_chat_session
from radar.core.chat.events import new_id, now_iso
from radar.core.config import RadarConfig
from radar.core.llm import LlmChatDelta, LlmChatDone, LlmChatResponse, LlmReasoningDelta, LlmToolCall
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages


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


def test_chat_run_store_appends_replayable_events(tmp_path):
    store = ChatRunStore(tmp_path / "chat")
    run = store.create_run(
        "session-1",
        metadata={"surface": "洞察"},
        request={"content": "继续处理"},
    )

    first = store.append_event(run.run_id, "session", {"session_id": "session-1"})
    second = store.append_event(run.run_id, "assistant_delta", {"content": "处理中"})

    assert first.seq == 1
    assert second.seq == 2
    assert (tmp_path / "chat" / "runs.sqlite3").exists()
    assert store.get_run(run.run_id).request == {"content": "继续处理"}
    assert [event.event for event in store.load_events(run.run_id)] == [
        "session",
        "assistant_delta",
    ]
    assert [event.event for event in store.load_events(run.run_id, after_seq=1)] == [
        "assistant_delta",
    ]
    assert store.active_run(session_id="session-1") is not None

    store.mark_completed(run.run_id)

    assert store.active_run(session_id="session-1") is None


def test_chat_run_store_claims_and_releases_leases(tmp_path):
    store = ChatRunStore(tmp_path / "chat")
    run = store.create_run("session-lease")

    claimed = store.claim_run(run.run_id, "worker-1", ttl_seconds=30)

    assert claimed is not None
    assert claimed.lease_owner == "worker-1"
    assert claimed.lease_until is not None
    assert store.claim_run(run.run_id, "worker-2", ttl_seconds=30) is None

    heartbeat = store.heartbeat(run.run_id, owner="worker-1", ttl_seconds=30)

    assert heartbeat.lease_owner == "worker-1"

    try:
        store.heartbeat(run.run_id, owner="worker-2", ttl_seconds=30)
    except ChatRunLeaseLost:
        pass
    else:
        raise AssertionError("heartbeat with the wrong lease owner should fail")

    store.release_lease(run.run_id, "worker-2")
    assert store.get_run(run.run_id).lease_owner == "worker-1"

    released = store.release_lease(run.run_id, "worker-1")

    assert released.lease_owner is None
    assert released.lease_until is None
    assert store.claim_run(run.run_id, "worker-2", ttl_seconds=30) is not None


def test_chat_run_store_cleans_terminal_runs(tmp_path):
    store = ChatRunStore(tmp_path / "chat")
    running = store.create_run("session-running")
    terminal_run_ids = []

    for index in range(3):
        run = store.create_run(f"session-{index}")
        store.append_event(run.run_id, "assistant_delta", {"content": str(index)})
        store.mark_completed(run.run_id)
        terminal_run_ids.append(run.run_id)

    deleted = store.cleanup_terminal_runs(keep_latest=1)

    assert deleted == 2
    assert store.get_run(running.run_id).status == "running"
    remaining_terminal_runs = [
        run for run in store.list_runs() if run.status in {"completed", "failed", "cancelled"}
    ]
    assert len(remaining_terminal_runs) == 1
    assert store.load_events(remaining_terminal_runs[0].run_id)

    deleted_run_ids = set(terminal_run_ids) - {remaining_terminal_runs[0].run_id}
    for run_id in deleted_run_ids:
        try:
            store.get_run(run_id)
        except FileNotFoundError:
            continue
        raise AssertionError("terminal run should have been deleted")


def test_can_continue_chat_session_detects_interrupted_turn(tmp_path):
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    user_message = ChatMessage(message_id=new_id(), role="user", content="查证据链", created_at=now_iso())
    store.append_message(session.session_id, user_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_started",
            created_at=now_iso(),
            payload={"user_message_id": user_message.message_id},
        )
    )

    assert can_continue_chat_session(store.load_events(session.session_id)) is True

    store.append_message(
        session.session_id,
        ChatMessage(message_id=new_id(), role="tool", content='{"items":[]}', created_at=now_iso()),
    )

    assert can_continue_chat_session(store.load_events(session.session_id)) is True

    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_completed",
            created_at=now_iso(),
            payload={"user_message_id": user_message.message_id},
        )
    )

    assert can_continue_chat_session(store.load_events(session.session_id)) is False


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


def test_chat_system_prompt_layers_surface_rules():
    common_prompt = build_chat_system_prompt()
    wechat_prompt = build_chat_system_prompt("微信会话")
    catalyst_prompt = build_chat_system_prompt("催化词")
    stock_prompt = build_chat_system_prompt("个股深挖")

    assert common_prompt == COMMON_CHAT_SYSTEM_PROMPT
    assert DEFAULT_CHAT_SYSTEM_PROMPT == COMMON_CHAT_SYSTEM_PROMPT
    assert "只做研究辅助和证据整理" in common_prompt
    assert "不输出买入、卖出、持有、仓位、目标价" in common_prompt
    assert "投资价值排序" in common_prompt
    assert "证据完整度、跟踪优先级" in common_prompt
    assert "多次调用 radar_search_messages / radar_get_conversation_window 和 radar_search_web" in common_prompt
    assert "本地消息用于定位线索，Brave Search 用于补公开来源" in common_prompt
    assert "radar_strategy_candidates / radar_theme_candidates" in common_prompt
    assert "不要一次性拉取完整证据链" in common_prompt
    assert "输出 Markdown 时使用标准语法" in common_prompt
    assert "不要写 `##标题` 或 `-内容`" in common_prompt
    assert "radar_strategy_candidates" in stock_prompt
    assert "radar_stock_evidence_detail" in stock_prompt
    assert "radar_theme_candidates" in stock_prompt
    assert "radar_get_conversation_window" in wechat_prompt
    assert "页面传入的 evidence" in wechat_prompt
    assert "暂缓跟踪条件" in wechat_prompt
    assert "已注入的页面上下文和原文证据" in catalyst_prompt
    assert "不要为了当前证据再调用工具" in catalyst_prompt
    assert "才调用 radar_scan_catalysts 扩展证据半径" in catalyst_prompt
    assert "才调用 radar_get_conversation_window" in catalyst_prompt
    assert "才调用 radar_list_catalyst_terms" in catalyst_prompt
    assert "radar_stock_evidence_chart" in stock_prompt
    assert "当前入口：个股深挖" in stock_prompt


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
    assert "radar_search_web" in tool_names
    assert "radar_get_conversation_window" in tool_names
    assert "radar_get_realtime_quote" in tool_names
    assert "radar_get_stock_price_history" in tool_names
    assert "radar_get_realtime_daily_quote" not in tool_names
    assert "radar_get_stock_moneyflow" in tool_names
    assert "radar_get_stock_technical_factors" in tool_names
    assert "radar_get_limit_pool" in tool_names
    assert "radar_strategy_candidates" in tool_names
    assert "radar_stock_evidence_detail" in tool_names
    assert "radar_theme_candidates" in tool_names
    assert "radar_stock_evidence_chart" in tool_names
    assert "radar_scan_catalysts" in tool_names
    assert "radar_list_catalyst_terms" in tool_names
    assert "radar_stock_evidence_chain" not in tool_names
    assert "radar_backtest_summary" not in tool_names
    assert "radar_analyst_backtest_summary" in tool_names
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
                _personal_message("p1", "2026-06-04T09:04:00", "张三", "私聊提到光模块"),
            ],
        )
    finally:
        conn.close()

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    search_result = agent.tools.get("radar_search_messages").execute({"keyword": "AI", "limit": 5})
    group_window_result = agent.tools.get("radar_get_conversation_window").execute(
        {"source": "个人群", "group_name": "东财策略", "limit": 5}
    )
    personal_window_result = agent.tools.get("radar_get_conversation_window").execute(
        {"source": "个人消息", "sender": "张三", "limit": 5}
    )
    context_result = agent.tools.get("radar_get_message_context").execute({"message_id": "m2", "radius": 2})
    conversations_result = agent.tools.get("radar_list_conversations").execute({"limit": 5})
    overview_result = agent.tools.get("radar_message_overview").execute({"days": 2, "top_limit": 5})

    assert [item["message_id"] for item in search_result["items"]] == ["m2", "m1"]
    assert [item["message_id"] for item in group_window_result["items"]] == ["m2", "m1"]
    assert group_window_result["items"][0]["content"] == "AI 继续发酵"
    assert [item["message_id"] for item in personal_window_result["items"]] == ["p1"]
    assert personal_window_result["items"][0]["content"] == "私聊提到光模块"
    assert context_result["target"]["message_id"] == "m2"
    assert [item["message_id"] for item in context_result["before"]] == ["m1"]
    assert [item["title"] for item in conversations_result["items"]] == ["张三", "其他群", "东财策略"]
    assert overview_result["summary"]["total_count"] == 4
    assert "anchor_heat" not in overview_result


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


def _personal_message(message_id: str, message_time: str, sender: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人消息",
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=None,
        fetch_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        fetch_window="20260604090000-20260604100000",
    )
