from __future__ import annotations

import json

import pytest

from radar.core.chat import ChatAgent, ChatSessionStore, parse_chat_skill
from radar.core.chat.skill_tools import build_skill_tools
from radar.core.chat.skills import ChatSkillLibrary
from radar.core.config import BUILTIN_CHAT_SKILLS_DIR, RadarConfig
from radar.core.llm import LlmChatResponse, LlmToolCall


def test_parse_chat_skill_reads_name_description_and_body(tmp_path):
    skill_dir = tmp_path / "skills" / "market"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: market_research
description: 行情研究
---
先确认标的，再读取行情数据。
""",
        encoding="utf-8",
    )

    skill = parse_chat_skill(skill_file)

    assert skill.name == "market_research"
    assert skill.description == "行情研究"
    assert "先确认标的" in skill.instructions
    assert skill.root_dir == skill_dir


def test_builtin_chat_skills_are_loaded_before_user_skills(tmp_path):
    user_skill_dir = tmp_path / "skills" / "market"
    user_skill_dir.mkdir(parents=True)
    (user_skill_dir / "SKILL.md").write_text(
        """---
name: market_research
description: 股票行情研究
---
读取本地行情。
""",
        encoding="utf-8",
    )

    skills = ChatSkillLibrary.from_config(RadarConfig(config_dir=tmp_path)).list()
    skill_by_name = {skill.name: skill for skill in skills}
    names = [skill.name for skill in skills]

    assert names.index("investment-valuation") < names.index("market_research")
    assert "catalyst-valuation-upside" in names
    assert skill_by_name["investment-valuation"].source_path.is_relative_to(BUILTIN_CHAT_SKILLS_DIR)
    assert skill_by_name["catalyst-valuation-upside"].source_path.is_relative_to(BUILTIN_CHAT_SKILLS_DIR)


def test_chat_agent_injects_skill_catalog_without_full_skill_body(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "market"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: market_research
description: 股票行情研究
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

    ChatAgent(config, store=store, enable_builtin_tools=False).run_turn(session.session_id, "帮我看一下行情")

    system_prompt = seen["messages"][0]["content"]
    assert "可用 skills 目录" in system_prompt
    assert "market_research: 股票行情研究" in system_prompt
    assert "如果用户没有提供股票名" not in system_prompt
    assert {tool.name for tool in seen["tools"]} == {
        "radar_list_skills",
        "radar_load_skill",
        "radar_read_skill_reference",
    }
    assert store.load_messages(session.session_id)[0].metadata["skills"] == []
    turn_started = [event for event in store.load_events(session.session_id) if event.type == "turn_started"][0]
    assert turn_started.payload["active_skills"] == []


def test_chat_agent_loads_skill_full_body_and_reference_list(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "market"
    reference_dir = skill_dir / "references"
    reference_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: market_research
description: 股票行情研究
---
如果用户没有提供股票名，先追问具体标的。
""",
        encoding="utf-8",
    )
    (reference_dir / "market.md").write_text("先看价格，再看消息。", encoding="utf-8")
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()
    calls = []

    def fake_chat_response(config, messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return LlmChatResponse(
                content="",
                tool_calls=[LlmToolCall("call-1", "radar_load_skill", {"name": "market_research"})],
            )
        return LlmChatResponse(content="已读取 skill", tool_calls=[])

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store, enable_builtin_tools=False).run_turn(
        session.session_id,
        "帮我看一下行情",
    )

    tool_messages = result.tool_messages
    payload = json.loads(tool_messages[0].content)
    assert payload["name"] == "market_research"
    assert "如果用户没有提供股票名" in payload["content"]
    assert payload["references"] == [{"path": "references/market.md", "size_bytes": 30}]


def test_skill_reference_tool_reads_relative_files_and_blocks_traversal(tmp_path):
    skill_dir = tmp_path / "skills" / "market"
    reference_dir = skill_dir / "references"
    reference_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: market_research
description: 股票行情研究
---
读取 references 获取细节。
""",
        encoding="utf-8",
    )
    (reference_dir / "market.md").write_text("先看价格，再看消息。", encoding="utf-8")
    library = ChatSkillLibrary.from_config(RadarConfig(config_dir=tmp_path))
    tools = {tool.name: tool for tool in build_skill_tools(library)}

    result = tools["radar_read_skill_reference"].execute(
        {"skill_name": "market_research", "path": "references/market.md"}
    )

    assert result["path"] == "references/market.md"
    assert result["content"] == "先看价格，再看消息。"
    with pytest.raises(ValueError, match="不能越过"):
        tools["radar_read_skill_reference"].execute({"skill_name": "market_research", "path": "../x.md"})
