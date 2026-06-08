from __future__ import annotations

from radar.core.chat import ChatAgent, ChatSessionStore, ChatTool, ExtensionContext, parse_chat_skill
from radar.core.config import RadarConfig
from radar.core.llm import LlmChatResponse, LlmToolCall


def test_parse_chat_skill_reads_frontmatter_and_body(tmp_path):
    skill_dir = tmp_path / "skills" / "market"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: market_research
description: 行情研究
triggers:
  - 行情
tools:
  - radar_resolve_stock
always_on: false
---
先确认标的，再读取行情数据。
""",
        encoding="utf-8",
    )

    skill = parse_chat_skill(skill_file)

    assert skill.name == "market_research"
    assert skill.description == "行情研究"
    assert skill.triggers == ("行情",)
    assert skill.tool_names == ("radar_resolve_stock",)
    assert "先确认标的" in skill.instructions


def test_chat_agent_injects_matching_skill_and_filters_tools(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "market"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: market_research
description: 股票行情研究
triggers:
  - 行情
tools:
  - radar_resolve_stock
---
如果用户没有提供股票名，先追问具体标的。
""",
        encoding="utf-8",
    )
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    seen = {}

    def fake_chat_response(config, messages, **kwargs):
        seen["messages"] = messages
        seen["tools"] = kwargs["tools"]
        return LlmChatResponse(content="请给股票名", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    ChatAgent(config, store=store).run_turn(session.session_id, "帮我看一下行情")

    assert "market_research" in seen["messages"][0]["content"]
    assert "如果用户没有提供股票名" in seen["messages"][0]["content"]
    assert [tool.name for tool in seen["tools"]] == ["radar_resolve_stock"]
    assert store.load_messages(session.session_id)[0].metadata["skills"] == ["market_research"]
    turn_started = [event for event in store.load_events(session.session_id) if event.type == "turn_started"][0]
    assert turn_started.payload["active_skills"] == ["market_research"]


def test_chat_agent_blocks_tool_not_allowed_by_active_skill(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "search"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: local_search
triggers:
  - 搜索
tools:
  - allowed_tool
---
只允许使用 allowed_tool。
""",
        encoding="utf-8",
    )
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    class TestExtension:
        name = "test"

        def register(self, context: ExtensionContext) -> None:
            context.register_tool(
                ChatTool(
                    name="allowed_tool",
                    description="允许的工具",
                    input_schema={"type": "object"},
                    handler=lambda args: {"ok": True},
                )
            )
            context.register_tool(
                ChatTool(
                    name="blocked_tool",
                    description="未授权工具",
                    input_schema={"type": "object"},
                    handler=lambda args: {"ok": False},
                )
            )

    def fake_chat_response(config, messages, **kwargs):
        calls.append(kwargs["tools"])
        if len(calls) == 1:
            return LlmChatResponse(content="", tool_calls=[LlmToolCall("call-1", "blocked_tool", {})])
        return LlmChatResponse(content="工具被拦截", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store, extensions=[TestExtension()], enable_builtin_tools=False).run_turn(
        session.session_id,
        "搜索一下",
    )

    messages = store.load_messages(session.session_id)
    assert [tool.name for tool in calls[0]] == ["allowed_tool"]
    assert result.assistant_message.content == "工具被拦截"
    assert messages[2].metadata["is_error"] is True
    assert "工具未被当前 skill 开放" in messages[2].content
