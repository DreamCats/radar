from radar.core.chat import ChatAgent, ChatSessionStore
from radar.core.chat.follow_up import build_follow_up_suggestion
from radar.core.config import RadarConfig
from radar.core.llm import LlmChatResponse


def test_follow_up_suggestion_prefers_stock_validation():
    suggestion = build_follow_up_suggestion(
        "从策略信号里筛 5 只股票",
        "1. 北方华创 (002371.SZ) 半导体设备主线。需要验证订单、长存 IPO 进展和行情确认。",
    )

    assert suggestion == "继续补北方华创的原文证据、行情确认和关键验证点。"


def test_follow_up_suggestion_falls_back_to_risk_layering():
    suggestion = build_follow_up_suggestion(
        "帮我排雷",
        "风险提示：有些方向已经兑现，部分标的还缺反证和成交量验证。",
    )

    assert suggestion == "把上面的风险按“立即暂缓、继续观察、可忽略”分层。"


def test_chat_agent_attaches_follow_up_suggestion_to_final_assistant_message(tmp_path, monkeypatch):
    config = RadarConfig(config_dir=tmp_path)
    store = ChatSessionStore(tmp_path / "chat")
    session = store.create_session()

    def fake_chat_response(config, messages, **kwargs):
        return LlmChatResponse(
            content="1. 北方华创 (002371.SZ) 半导体设备主线。需要验证订单和行情确认。",
            tool_calls=[],
        )

    monkeypatch.setattr("radar.core.chat.agent.chat_response", fake_chat_response)

    result = ChatAgent(config, store=store, enable_builtin_tools=False).run_turn(
        session.session_id,
        "筛选跟踪标的",
    )

    assert (
        result.assistant_message.metadata["follow_up_suggestion"]
        == "继续补北方华创的原文证据、行情确认和关键验证点。"
    )
