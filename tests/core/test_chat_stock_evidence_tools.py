from __future__ import annotations

from datetime import datetime

from radar.core.chat import ChatAgent, ChatSessionStore
from radar.core.config import RadarConfig
from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)
from radar.core.usecases.stock_evidence_chain.stock_chart import (
    StockEvidenceStockCandle,
    StockEvidenceStockChart,
)
from radar.core.usecases.stock_evidence_chain.views import (
    StockEvidenceChainDashboard,
    StockEvidenceChainItem,
)


def test_stock_evidence_tools_split_candidates_detail_and_theme(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    now = datetime.fromisoformat("2026-06-10T10:00:00")
    dashboard = StockEvidenceChainDashboard(
        as_of_time=now,
        generated_at=now,
        item_count=3,
        stage_counts={"pricing": 1, "spreading": 1, "seed": 1},
        items=[
            _stock_evidence_item("002138.SZ", "顺络电子", "pricing", now, theme_name="AI硬件"),
            _stock_evidence_item("002371.SZ", "北方华创", "spreading", now, theme_name="半导体设备"),
            _stock_evidence_item("600188.SH", "兖矿能源", "seed", now, theme_name="煤炭"),
        ],
    )
    monkeypatch.setattr(
        "radar.core.chat.stock_evidence_tools.latest_stock_evidence_chain",
        lambda config, *, limit: dashboard,
    )

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    candidates = agent.tools.get("radar_strategy_candidates").execute({"limit": 2})
    detail = agent.tools.get("radar_stock_evidence_detail").execute({"stock": "顺络", "limit": 5})
    themes = agent.tools.get("radar_theme_candidates").execute({"theme": "半导体", "limit": 5})

    assert candidates["item_count"] == 2
    assert candidates["stage_counts"] == {"pricing": 1, "spreading": 1}
    assert candidates["items"][0]["ts_code"] == "002138.SZ"
    assert "evidence_chain" not in candidates["items"][0]
    assert detail["found"] is True
    assert detail["items"][0]["ts_code"] == "002138.SZ"
    assert detail["items"][0]["theme"]["theme_name"] == "AI硬件"
    assert themes["theme_count"] == 1
    assert themes["themes"][0]["theme_name"] == "半导体设备"
    assert themes["themes"][0]["candidates"][0]["ts_code"] == "002371.SZ"


def test_stock_evidence_chart_tool_returns_strategy_chart_summary(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}
    monkeypatch.setattr("radar.core.chat.stock_evidence_tools.resolve_stock", lambda config, value: "002138.SZ")

    def fake_chart(config, *, ts_code, days):
        captured.update({"ts_code": ts_code, "days": days})
        return StockEvidenceStockChart(
            ts_code=ts_code,
            candles=[
                _candle("20260605", 10.0, 10.8, 9.8, 10.5, amount=10000),
                _candle("20260606", 10.5, 12.0, 10.4, 11.5, amount=30000),
            ],
            latest_trade_date="20260606",
        )

    monkeypatch.setattr("radar.core.chat.stock_evidence_tools.get_stock_evidence_stock_chart", fake_chart)

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    result = agent.tools.get("radar_stock_evidence_chart").execute({"stock": "顺络电子", "days": 2})

    assert captured == {"ts_code": "002138.SZ", "days": 2}
    assert result["found"] is True
    assert result["stock"] == "顺络电子"
    assert result["ts_code"] == "002138.SZ"
    assert [item["trade_date"] for item in result["candles"]] == ["20260605", "20260606"]
    assert result["summary"]["return_from_first"] == 0.0952
    assert result["summary"]["latest_amount_vs_avg20"] == 0.5


def _stock_evidence_item(
    ts_code: str,
    stock_name: str,
    stage: str,
    now: datetime,
    *,
    theme_name: str | None = None,
) -> StockEvidenceChainItem:
    theme = (
        StockEvidenceThemeContext(
            theme_id=f"theme:{theme_name}",
            theme_name=theme_name,
            theme_type="theme",
            role="main",
            confidence=0.8,
            source_count=2,
            quality_label="主线候选",
        )
        if theme_name
        else None
    )
    return StockEvidenceChainItem(
        ts_code=ts_code,
        stock_name=stock_name,
        stage=stage,
        stage_label=stage,
        confidence=0.8,
        rank=1,
        summary=f"{stock_name} 证据链",
        trigger_count=1,
        unique_trigger_count=1,
        sender_count=1,
        conversation_count=1,
        evidence_count=1,
        why=[f"{stock_name} 出现多条策略证据"],
        pricing_risk="已有部分定价",
        watch_next=["观察成交额持续性"],
        themes=[theme] if theme else [],
        primary_theme=theme,
        recognition=StockEvidenceRecognitionContext(state="just_confirmed", state_label="刚确认"),
        updated_at=now,
    )


def _candle(
    trade_date: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    *,
    amount: float,
) -> StockEvidenceStockCandle:
    return StockEvidenceStockCandle(
        trade_date=trade_date,
        open=open_price,
        high=high,
        low=low,
        close=close,
        pre_close=open_price,
        change=close - open_price,
        pct_chg=round(((close - open_price) / open_price) * 100, 2),
        vol=1000,
        amount=amount,
    )
