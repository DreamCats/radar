from __future__ import annotations

import threading
import time
from datetime import date, datetime

from radar.core.config import RadarConfig
from radar.core.market.quotes import RealtimeQuote
from radar.core.messages import CatalystCategory, CatalystStockMention, CatalystTermLibrary, save_catalyst_terms
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.usecases.catalyst_strategy import (
    CatalystStockAnalysis,
    CatalystStrategyEvidence,
    FinancialTrendPoint,
    MarketSnapshot,
    run_catalyst_strategy_report,
)
from radar.core.usecases.catalyst_strategy.analyze import analyze_stock_context
from radar.core.usecases.catalyst_strategy.market import load_market_snapshot


def test_market_snapshot_estimates_intraday_market_cap_and_pe(monkeypatch, tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path})

    def fake_quote(config, *, ts_code, sources=("tencent", "sina")):
        return RealtimeQuote(
            ts_code=ts_code,
            source="tencent",
            name="测试股票",
            close=12.0,
            open=11.0,
            timestamp="2026-06-28 10:30:00",
        )

    def fake_tushare_call(config, api_name, params=None, fields=None, *, cache_ttl=None, use_cache=True):
        if api_name == "daily_basic":
            return [
                {
                    "ts_code": "300476.SZ",
                    "trade_date": "20260626",
                    "close": 10.0,
                    "pe": 30.0,
                    "pe_ttm": 20.0,
                    "total_share": 100000.0,
                    "total_mv": 1000000.0,
                    "circ_mv": 800000.0,
                },
                {"ts_code": "300476.SZ", "trade_date": "20260625", "pe_ttm": 10.0},
                {"ts_code": "300476.SZ", "trade_date": "20260624", "pe_ttm": 30.0},
            ]
        assert api_name == "income"
        return [
            {
                "ts_code": "300476.SZ",
                "end_date": "20251231",
                "ann_date": "20260330",
                "total_revenue": 8_000_000_000.0,
                "n_income_attr_p": 1_000_000_000.0,
            },
            {
                "ts_code": "300476.SZ",
                "end_date": "20241231",
                "ann_date": "20250330",
                "total_revenue": 6_000_000_000.0,
                "n_income_attr_p": 700_000_000.0,
            },
            {
                "ts_code": "300476.SZ",
                "end_date": "20231231",
                "ann_date": "20240330",
                "total_revenue": 4_000_000_000.0,
                "n_income_attr_p": 400_000_000.0,
            },
        ]

    monkeypatch.setattr("radar.core.usecases.catalyst_strategy.market.get_public_realtime_quote", fake_quote)
    monkeypatch.setattr("radar.core.usecases.catalyst_strategy.market.tushare_call", fake_tushare_call)

    snapshot = load_market_snapshot(
        config,
        _context("300476.SZ", "胜宏科技"),
        today=date(2026, 6, 28),
    )

    assert snapshot.price_basis == "realtime"
    assert snapshot.valuation_basis == "realtime_estimated"
    assert snapshot.estimated_total_mv_yi == 120.0
    assert snapshot.total_mv_yi == 100.0
    assert snapshot.estimated_pe == 36.0
    assert snapshot.estimated_pe_ttm == 24.0
    assert snapshot.implied_net_profit_ttm_yi == 5.0
    assert round(snapshot.pe_ttm_percentile_60d or 0, 2) == 66.67
    assert snapshot.latest_financial_period == "20251231"
    assert snapshot.latest_revenue_yi == 80.0
    assert snapshot.latest_net_profit_yi == 10.0
    assert [item.period for item in snapshot.financial_trend] == ["20251231", "20241231", "20231231"]


def test_catalyst_strategy_run_generates_html_without_publishing(monkeypatch, tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    save_catalyst_terms(
        config,
        CatalystTermLibrary(
            categories=[CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["新签订单"])]
        ),
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message(
                    "m1",
                    "2026-06-28T09:30:00",
                    "东财策略",
                    "胜宏科技 新签订单 10 亿，产能继续释放。",
                )
            ],
        )
    finally:
        conn.close()

    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.collect.load_catalyst_stock_detector",
        lambda _config: lambda _text: [CatalystStockMention(ts_code="300476.SZ", stock_name="胜宏科技")],
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.load_market_snapshot",
        lambda _config, context: MarketSnapshot(
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            realtime_price=12.0,
            estimated_total_mv_yi=120.0,
            estimated_pe_ttm=24.0,
            implied_net_profit_ttm_yi=5.0,
            pe_ttm_percentile_250d=66.7,
            latest_financial_period="20251231",
            latest_revenue_yi=80.0,
            latest_net_profit_yi=10.0,
            financial_trend=[
                FinancialTrendPoint(period="20251231", revenue_yi=80.0, net_profit_yi=10.0),
            ],
            price_basis="realtime",
            valuation_basis="realtime_estimated",
        ),
    )

    def fake_analyze(config, context, *, provider_name=None, model=None):
        return CatalystStockAnalysis(
            stock_key=context.stock_key,
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            summary=["订单催化明确。", "市场快照已补充。", "估值需要继续验证。"],
            valuation_status="provided",
            valuation_text="目标市值 180 亿，上涨空间 50%。",
            target_market_cap_yi=180.0,
            target_price=18.0,
            upside_pct=50.0,
            confidence="中",
            risks=["订单交付节奏低于预期"],
        )

    monkeypatch.setattr("radar.core.usecases.catalyst_strategy.runner.analyze_stock_context", fake_analyze)

    result = run_catalyst_strategy_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        publish=False,
        notify=False,
    )

    assert result.report.total_stocks == 1
    assert result.published_url is None
    assert result.bark_sent is False
    html = result.local_html_path.read_text(encoding="utf-8")
    assert "胜宏科技" in html
    assert "首提：06-28 09:30" in html
    assert "个人群 / tester / 东财策略" in html
    assert "订单催化明确" in html
    assert '<span class="stock-highlight">胜宏科技</span>' in html
    assert '<span class="term-highlight">新签订单</span>' in html
    assert '<span class="number-highlight">180 亿</span>' in html
    assert "180.00 亿" in html
    assert "TTM隐含利润" in html
    assert "20251231 10.00 亿" in html
    assert "财报期" in html


def test_catalyst_strategy_skips_publish_and_notify_when_empty(monkeypatch, tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    publish_calls: list[object] = []
    notify_calls: list[object] = []

    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.collect_catalyst_stock_contexts",
        lambda config, *, start_time, end_time, limit, max_stocks: ([], 0),
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.publish_report_html",
        lambda *args, **kwargs: publish_calls.append((args, kwargs)) or "https://example.com/report.html",
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.notify_report",
        lambda *args, **kwargs: notify_calls.append((args, kwargs)),
    )

    result = run_catalyst_strategy_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        publish=True,
        notify=True,
    )

    assert result.report.total_stocks == 0
    assert result.published_url is None
    assert result.bark_sent is False
    assert result.local_html_path.exists()
    assert publish_calls == []
    assert notify_calls == []


def test_catalyst_strategy_analyzes_stocks_with_limited_concurrency(monkeypatch, tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    contexts = [
        _context("300001.SZ", "测试一"),
        _context("300002.SZ", "测试二"),
        _context("300003.SZ", "测试三"),
    ]
    active_count = 0
    max_active_count = 0
    lock = threading.Lock()

    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.collect_catalyst_stock_contexts",
        lambda config, *, start_time, end_time, limit, max_stocks: (contexts, len(contexts)),
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_strategy.runner.load_market_snapshot",
        lambda _config, context: None,
    )

    def fake_analyze(config, context, *, provider_name=None, model=None):
        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        time.sleep(0.02)
        with lock:
            active_count -= 1
        return CatalystStockAnalysis(
            stock_key=context.stock_key,
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            summary=[context.stock_name],
            valuation_status="skipped",
        )

    monkeypatch.setattr("radar.core.usecases.catalyst_strategy.runner.analyze_stock_context", fake_analyze)

    result = run_catalyst_strategy_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        llm_concurrency=2,
    )

    assert result.report.total_stocks == 3
    assert max_active_count == 2
    assert [analysis.stock_name for analysis in result.report.analyses] == ["测试一", "测试二", "测试三"]


def test_catalyst_strategy_analysis_disables_thinking(monkeypatch, tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    captured: dict[str, object] = {}

    def fake_chat_json(config, messages, **kwargs):
        captured.update(kwargs)
        return {
            "summary": ["测试一被提出。", "核心催化待验证。", "市场快照待补充。"],
            "valuation_status": "scenario",
            "valuation_text": "原文只有订单 10 亿，按转收入和净利率做情景推演。",
        }

    monkeypatch.setattr("radar.core.usecases.catalyst_strategy.analyze.chat_json", fake_chat_json)

    context = _context("300001.SZ", "测试一")
    context.evidence.append(
        CatalystStrategyEvidence(
            message_id="m1",
            source="个人群",
            sender="tester",
            message_time=datetime.fromisoformat("2026-06-28T10:00:00"),
            latest_message_time=datetime.fromisoformat("2026-06-28T10:00:00"),
            content="测试一 新签订单 10 亿。",
            matched_terms=["新签订单"],
        )
    )
    analysis = analyze_stock_context(config, context)

    assert analysis.stock_name == "测试一"
    assert analysis.valuation_status == "scenario"
    assert captured["disable_thinking"] is True
    assert "enable_thinking" not in captured


def _context(ts_code: str, stock_name: str):
    from radar.core.usecases.catalyst_strategy.models import CatalystStockContext

    now = datetime.fromisoformat("2026-06-28T10:00:00")
    return CatalystStockContext(
        stock_key=ts_code,
        ts_code=ts_code,
        stock_name=stock_name,
        first_message_time=now,
        latest_message_time=now,
    )


def _message(message_id: str, message_time: str, group_name: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        fetch_window="20260628090000-20260628100000",
    )
