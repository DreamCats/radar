from __future__ import annotations

from datetime import datetime

from radar.core.channel import BarkHttpError
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
from radar.core.usecases.catalyst_valuation_report.rules import (
    filter_contexts_by_valuation_evidence,
    match_valuation_evidence,
)


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
    assert "navigator.clipboard?.writeText" in html
    assert 'document.execCommand("copy")' in html
    assert "await copyText(text)" in html
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


def test_catalyst_valuation_report_default_does_not_cap_stocks(monkeypatch, tmp_path):
    config = _config(tmp_path)
    _save_terms(config)
    _insert_messages(
        config,
        [
            _message("m1", "2026-06-28T09:30:00", "胜宏科技 新签订单 10 亿。"),
            _message("m2", "2026-06-28T09:35:00", "测试二 新签订单 20 亿。"),
            _message("m3", "2026-06-28T09:40:00", "测试三 新签订单 30 亿。"),
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
    capped = run_catalyst_valuation_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        max_stocks=2,
        publish=False,
        notify=False,
    )

    assert result.report.total_stocks == 3
    assert capped.report.total_stocks == 2


def test_catalyst_valuation_report_filters_comparison_only_multi_stock_contexts():
    result = filter_contexts_by_valuation_evidence(
        [
            _valuation_context(
                "胜科纳米",
                "胜科纳米近300亿市值，【苏试试验】传统主业+航天业务+宜特目前仅100亿市值。",
                stock_mentions_count=2,
            ),
            _valuation_context(
                "福赛科技",
                "#福赛科技：首单120MW落地，正式接单交付，年底目标单周2000台。#晋拓股份：订单超1e。",
                stock_mentions_count=2,
            ),
        ]
    )

    assert [item.stock_name for item in result] == ["福赛科技"]
    assert result[0].evidence[0].valuation_numbers == ["120MW", "2000台"]


def test_catalyst_valuation_report_sorts_before_report_json():
    result = filter_contexts_by_valuation_evidence(
        [
            _valuation_context("市值票", "市值票 目标150亿市值。", message_time="2026-06-28T09:50:00"),
            _valuation_context("订单票", "订单票 新签订单10亿。", message_time="2026-06-28T09:40:00"),
            _valuation_context(
                "重复票",
                ["重复票 新签订单5亿。", "重复票 新增合同6亿。"],
                message_time="2026-06-28T09:20:00",
            ),
            _valuation_context(
                "混合票",
                ["混合票 目标150亿市值。", "混合票 新签订单8亿。"],
                message_time="2026-06-28T09:10:00",
            ),
        ]
    )

    assert [item.stock_name for item in result] == ["重复票", "混合票", "订单票", "市值票"]
    assert result[1].evidence[0].valuation_numbers == ["8亿"]


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


def test_catalyst_valuation_report_keeps_report_when_bark_fails(monkeypatch, tmp_path):
    config = _config(tmp_path)
    context = CatalystValuationStockContext(
        stock_key="300476.SZ",
        ts_code="300476.SZ",
        stock_name="胜宏科技",
        first_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
        latest_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
        evidence=[],
    )

    def fake_notify(*args, **kwargs):
        raise BarkHttpError("调用 Bark 超时")

    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.collect_catalyst_valuation_contexts",
        lambda config, *, start_time, end_time, limit, max_stocks: ([context], 4, 3),
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.publish_report_html",
        lambda *args, **kwargs: "https://example.com/report.html",
    )
    monkeypatch.setattr(
        "radar.core.usecases.catalyst_valuation_report.runner.notify_report",
        fake_notify,
    )

    result = run_catalyst_valuation_report(
        config,
        start_time=datetime.fromisoformat("2026-06-28T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:00:00"),
        publish=True,
        notify=True,
    )

    assert result.report.total_feed_items == 4
    assert result.report.total_candidate_stocks == 3
    assert result.report.total_stocks == 1
    assert result.local_html_path.exists()
    assert result.published_url == "https://example.com/report.html"
    assert result.bark_sent is False
    assert result.bark_error == "调用 Bark 超时"


def test_valuation_rule_rejects_percent_only_but_keeps_percent_with_money_anchor():
    assert (
        match_valuation_evidence(
            "行动教育 合同负债增长 45%，毛利率 78%。",
            stock_name="行动教育",
            ts_code="605098.SH",
            stock_mentions_count=1,
        )
        is None
    )
    anchored = match_valuation_evidence(
        "行动教育 新签合同 10亿元，毛利率 78%。",
        stock_name="行动教育",
        ts_code="605098.SH",
        stock_mentions_count=1,
    )
    assert anchored is not None
    assert anchored.numbers == ["10亿元", "78%"]
    assert (
        match_valuation_evidence(
            "行动教育 大涨 10%，成交额放量。",
            stock_name="行动教育",
            ts_code="605098.SH",
            stock_mentions_count=1,
        )
        is None
    )


def test_valuation_rule_rejects_price_only_and_multiple_only_noise():
    assert (
        match_valuation_evidence(
            "永安期货 最新股价16.48元，价格表现强势。",
            stock_name="永安期货",
            ts_code="600927.SH",
            stock_mentions_count=1,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "中国人寿 估值0.4倍，PB分位较低。",
            stock_name="中国人寿",
            ts_code="601628.SH",
            stock_mentions_count=1,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "卓创资讯 产品价格4.9万元/吨，价格继续上涨。",
            stock_name="卓创资讯",
            ts_code="301299.SZ",
            stock_mentions_count=1,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "华海诚科 产品价格37.91元，功率4kw。",
            stock_name="华海诚科",
            ts_code="688535.SH",
            stock_mentions_count=1,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "银轮股份 收入主要增长动能来自三条增长曲线。",
            stock_name="银轮股份",
            ts_code="002126.SZ",
            stock_mentions_count=1,
        )
        is None
    )
    anchored = match_valuation_evidence(
        "正帆科技 净利2e，给40倍估值。",
        stock_name="正帆科技",
        ts_code="688596.SH",
        stock_mentions_count=1,
    )
    assert anchored is not None
    assert anchored.numbers == ["2e", "40倍"]


def test_valuation_rule_filters_low_quality_numbers_from_mixed_evidence():
    financial = match_valuation_evidence(
        "瑞联新材 2026Q1营收3.79亿元，EPS 2.9元，毛利率53.35%，给20倍PE。",
        stock_name="瑞联新材",
        ts_code="688550.SH",
        stock_mentions_count=1,
    )
    assert financial is not None
    assert financial.numbers == ["3.79亿元", "53.35%", "20倍"]

    spec = match_valuation_evidence(
        "唯特偶 800G/1.6T出货大幅增加，3.2G主要用T8，订单金额1000万元。",
        stock_name="唯特偶",
        ts_code="301319.SZ",
        stock_mentions_count=1,
    )
    assert spec is not None
    assert spec.numbers == ["1000万元"]

    capacity = match_valuation_evidence(
        "长源东谷 首单120MW落地，未来储备约1GW。",
        stock_name="长源东谷",
        ts_code="603950.SH",
        stock_mentions_count=1,
    )
    assert capacity is not None
    assert capacity.numbers == ["120MW", "1GW"]

    quantity = match_valuation_evidence(
        "广立微 产能新增1台设备，客户后续规划235台。",
        stock_name="广立微",
        ts_code="301095.SZ",
        stock_mentions_count=1,
    )
    assert quantity is not None
    assert quantity.numbers == ["235台"]


def test_valuation_rule_filters_source_role_stock_mentions():
    assert (
        match_valuation_evidence(
            "🌈今日｜【中金公司】来福谐波董事长交流：2025年营收2.6e，谐波出货29w台。",
            stock_name="中金公司",
            ts_code="601995.SH",
            stock_mentions_count=1,
        )
        is None
    )

    target = match_valuation_evidence(
        "【华泰医药代雯团队】科伦药业点评：主业利润拐点已至，估测全年主业实现20亿利润。",
        stock_name="科伦药业",
        ts_code="002422.SZ",
        stock_mentions_count=1,
    )
    assert target is not None
    assert target.numbers == ["20亿"]

    own_title = match_valuation_evidence(
        "【迈为股份】董事长交流：半导体新签订单10亿，客户验证顺利。",
        stock_name="迈为股份",
        ts_code="300751.SZ",
        stock_mentions_count=1,
    )
    assert own_title is not None
    assert own_title.numbers == ["10亿"]


def test_valuation_rule_requires_local_window_for_multi_stock_fanout():
    assert (
        match_valuation_evidence(
            "应流股份未来燃机交付量有望提升到10亿元以上，此外建议关注上海电气、东方电气。",
            stock_name="上海电气",
            ts_code="601727.SH",
            stock_mentions_count=3,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "光刻胶产能500吨/年，已供货中芯国际、长电科技。",
            stock_name="中芯国际",
            ts_code="688981.SH",
            stock_mentions_count=2,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "子公司已成功进入京东方和沃格光电等头部客户，27年对应收入超10亿。",
            stock_name="沃格光电",
            ts_code="603773.SH",
            stock_mentions_count=2,
        )
        is None
    )
    assert (
        match_valuation_evidence(
            "紫光国微与宁德时代合资设立车规级MCU公司，汽车安全芯片累计出货突破千万颗。",
            stock_name="宁德时代",
            ts_code="300750.SZ",
            stock_mentions_count=2,
        )
        is None
    )
    match = match_valuation_evidence(
        "胜科纳米近300亿市值，【苏试试验】传统主业+航天业务+宜特目前仅100亿市值。",
        stock_name="苏试试验",
        ts_code="300416.SZ",
        stock_mentions_count=2,
    )
    assert match is not None
    assert match.numbers == ["100亿"]
    local_item = match_valuation_evidence(
        "#福赛科技：塑料件正式接单交付，年底目标单周2000台。#晋拓股份：订单超1e。",
        stock_name="福赛科技",
        ts_code="301529.SZ",
        stock_mentions_count=2,
    )
    assert local_item is not None
    assert local_item.numbers == ["2000台"]


def test_valuation_rule_accepts_e_as_yi_money_unit():
    match = match_valuation_evidence(
        "胜宏科技 新签订单 500e，产能继续释放。",
        stock_name="胜宏科技",
        ts_code="300476.SZ",
        stock_mentions_count=1,
    )

    assert match is not None
    assert match.numbers == ["500e"]
    assert (
        match_valuation_evidence(
            "胜宏科技 技术参数 1e9，客户验证通过。",
            stock_name="胜宏科技",
            ts_code="300476.SZ",
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


def _valuation_context(
    stock_name: str,
    contents: str | list[str],
    *,
    message_time: str = "2026-06-28T09:30:00",
    stock_mentions_count: int = 1,
) -> CatalystValuationStockContext:
    content_items = [contents] if isinstance(contents, str) else contents
    evidence = [
        CatalystValuationEvidence(
            message_id=f"evidence-{index}",
            source="个人群",
            sender="tester",
            group_name="东财策略",
            message_time=datetime.fromisoformat(message_time),
            latest_message_time=datetime.fromisoformat(message_time),
            content=content,
            stock_mentions_count=stock_mentions_count,
        )
        for index, content in enumerate(content_items, start=1)
    ]
    return CatalystValuationStockContext(
        stock_key=stock_name,
        stock_name=stock_name,
        first_message_time=min(item.message_time for item in evidence),
        latest_message_time=max(item.latest_message_time for item in evidence),
        evidence=evidence,
    )


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
