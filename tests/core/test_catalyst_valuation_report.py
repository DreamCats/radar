from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.messages import CatalystCategory, CatalystStockMention, CatalystTermLibrary, save_catalyst_terms
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.usecases.catalyst_valuation_report import run_catalyst_valuation_report
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationReport,
    CatalystValuationStockContext,
)
from radar.core.usecases.catalyst_valuation_report.render import render_report_html
from radar.core.usecases.catalyst_valuation_report.rules import match_valuation_evidence


def test_catalyst_valuation_report_filters_non_numeric_noise(monkeypatch, tmp_path):
    config = _config(tmp_path)
    _save_terms(config)
    _insert_messages(
        config,
        [
            _message("m1", "2026-06-28T09:30:00", "胜宏科技 新签订单 10 亿，产能继续释放。"),
            _message("m2", "2026-06-28T09:40:00", "测试二 国产替代突破，客户验证通过。"),
            _message("m3", "2026-06-28T09:50:00", "测试三 涨停 10%，市场情绪强。"),
        ],
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.collect.load_catalyst_stock_detector",
        lambda _config: _detector,
    )

    result = run_catalyst_valuation_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        publish=False,
        notify=False,
    )

    assert result.report.total_candidate_stocks == 3
    assert result.report.total_stocks == 1
    assert result.report.stocks[0].stock_name == "胜宏科技"
    assert result.report.stocks[0].evidence[0].valuation_numbers == ["10 亿"]
    html = result.local_html_path.read_text(encoding="utf-8")
    assert "Radar 催化估值线索报告" in html
    assert "胜宏科技" in html
    assert "测试二" not in html
    assert "测试三" not in html
    assert '<span class="number-highlight">10 亿</span>' in html
    assert "data-copy-evidence" in html
    assert "data-view-evidence" in html
    assert 'class="evidence-preview"' in html
    assert 'class="evidence-full" hidden' in html
    assert result.published_url is None
    assert result.bark_sent is False


def test_catalyst_valuation_report_requires_stock_local_numbers_for_multi_stock(monkeypatch, tmp_path):
    config = _config(tmp_path)
    _save_terms(config)
    _insert_messages(
        config,
        [
            _message(
                "m1",
                "2026-06-28T09:30:00",
                "胜宏科技 新签订单 10 亿；测试二 国产替代突破。",
            )
        ],
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.collect.load_catalyst_stock_detector",
        lambda _config: _detector,
    )

    result = run_catalyst_valuation_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        publish=False,
        notify=False,
    )

    assert result.report.total_candidate_stocks == 2
    assert [item.stock_name for item in result.report.stocks] == ["胜宏科技"]


def test_catalyst_valuation_report_skips_publish_and_notify_when_empty(monkeypatch, tmp_path):
    config = _config(tmp_path)
    publish_calls: list[object] = []
    notify_calls: list[object] = []

    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.collect_catalyst_valuation_contexts",
        lambda config, *, start_time, end_time, limit, max_stocks: ([], 0, 0),
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.publish_report_html",
        lambda *args, **kwargs: publish_calls.append((args, kwargs)) or "https://example.com/report.html",
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.notify_report",
        lambda *args, **kwargs: notify_calls.append((args, kwargs)),
    )

    result = run_catalyst_valuation_report(
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


def test_valuation_rule_accepts_business_percent_but_rejects_market_percent():
    assert match_valuation_evidence(
        "行动教育 合同负债增长 45%，毛利率 78%。",
        stock_name="行动教育",
        ts_code="605098.SH",
        stock_mentions_count=1,
    )
    assert (
        match_valuation_evidence(
            "行动教育 大涨 10%，成交额放量。",
            stock_name="行动教育",
            ts_code="605098.SH",
            stock_mentions_count=1,
        )
        is None
    )


def test_valuation_rule_rejects_market_size_and_value_ratio_noise():
    assert (
        match_valuation_evidence(
            "汇成真空 AI硬件链真正稀缺且卡位好低估龙头\n"
            "独占TGV工序40%价值量\n"
            "GKJ镀膜独家设备供应商\n"
            "光通信千亿市场订单放量中，客户十倍级增量反转。",
            stock_name="汇成真空",
            ts_code="301392.SZ",
            stock_mentions_count=1,
        )
        is None
    )


def test_report_highlights_display_numbers_without_using_them_as_filter_basis():
    report = CatalystValuationReport(
        generated_at=datetime.fromisoformat("2026-06-28T10:00:00"),
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        total_feed_items=1,
        total_candidate_stocks=1,
        total_stocks=1,
        stocks=[
            CatalystValuationStockContext(
                stock_key="688146.SH",
                ts_code="688146.SH",
                stock_name="中船特气",
                first_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                latest_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                evidence=[
                    CatalystValuationEvidence(
                        message_id="m1",
                        source="个人群",
                        sender="tester",
                        group_name="东财策略",
                        message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                        latest_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                        content="中船特气 收入测算，电子大宗气体市场规模预计2028年增长至256亿元。",
                        matched_terms=["收入", "测算"],
                        valuation_terms=["收入"],
                        valuation_numbers=["23%"],
                    )
                ],
            )
        ],
    )

    html = render_report_html(report)

    assert '<span class="number-highlight">256亿元</span>' in html
    assert "查看原文" in html
    assert '<pre class="evidence-preview">' in html
    assert "2028年增长至....." in html
    assert 'class="evidence-full" hidden' in html


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})


def _save_terms(config: RadarConfig) -> None:
    save_catalyst_terms(
        config,
        CatalystTermLibrary(
            categories=[
                CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["新签订单"]),
                CatalystCategory(id="technology", name="技术", color="#a78bfa", terms=["国产替代", "突破"]),
                CatalystCategory(id="market", name="行情", color="#f6465d", terms=["涨停", "放量"]),
            ]
        ),
    )


def _insert_messages(config: RadarConfig, messages: list[RawMessage]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
    finally:
        conn.close()


def _detector(text: str) -> list[CatalystStockMention]:
    result: list[CatalystStockMention] = []
    if "胜宏科技" in text:
        result.append(CatalystStockMention(ts_code="300476.SZ", stock_name="胜宏科技"))
    if "测试二" in text:
        result.append(CatalystStockMention(ts_code="300002.SZ", stock_name="测试二"))
    if "测试三" in text:
        result.append(CatalystStockMention(ts_code="300003.SZ", stock_name="测试三"))
    return result


def _message(message_id: str, message_time: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name="东财策略",
        fetch_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        fetch_window="20260628090000-20260628100000",
    )
