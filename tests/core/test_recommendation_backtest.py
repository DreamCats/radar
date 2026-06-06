from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.models import MessageAnchor, MessageClassification, RawMessage
from radar.core.store import (
    connect,
    init_db,
    replace_message_anchors,
    upsert_message_classifications,
    upsert_messages,
)
from radar.core.usecases.recommendation_backtest import (
    refresh_recommendation_backtests,
    summarize_recommendation_backtests,
)


def test_refresh_recommendation_backtests_builds_events_and_windows(monkeypatch, tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    _seed_messages(
        config,
        [
            _message("m1", "2026-05-01T10:00:00", "分析师推荐贵州茅台，继续买入。", sender="张三-分析师"),
            _message("m2", "2026-05-01T10:05:00", "贵州茅台研究更新。", sender="李四-研究员"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "recommendation", 0.92),
            _classification("m2", "research", 0.95),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [
                _anchor("m1", "stock:600519.SH", "stock", "贵州茅台", 0.99),
                _anchor("m1", "industry:白酒", "industry", "白酒", 0.88),
            ],
            "m2": [_anchor("m2", "stock:600519.SH", "stock", "贵州茅台", 0.99)],
        },
    )
    market_calls = []

    def fake_market_call(config, api_name, params=None, fields=None, *, cache_ttl=None, use_cache=True):
        market_calls.append((api_name, dict(params or {})))
        return _fake_market_call(config, api_name, params, fields, cache_ttl=cache_ttl, use_cache=use_cache)

    monkeypatch.setattr("radar.core.usecases.recommendation_backtest.refresh.call", fake_market_call)

    result = refresh_recommendation_backtests(
        config,
        as_of=date(2026, 5, 8),
        window_days=10,
        windows=[1, 2, 3, 5],
        extractor_version="test-anchor",
    )

    assert result.event_count == 1
    assert result.inserted_event_count == 1
    assert result.refreshed_count == 4
    assert result.pending_count == 0
    assert result.missing_price_count == 0
    price_calls = [(api_name, params["ts_code"]) for api_name, params in market_calls if api_name in {"daily", "index_daily"}]
    assert price_calls == [("daily", "600519.SH"), ("index_daily", "000300.SH")]

    summary = summarize_recommendation_backtests(
        config,
        start_time=datetime.fromisoformat("2026-04-29T00:00:00"),
        end_time=datetime.fromisoformat("2026-05-09T00:00:00"),
        group_by="source_stock",
    )
    assert summary.row_count == 1
    row = summary.rows[0]
    assert row.source_candidate == "张三-分析师"
    assert row.ts_code == "600519.SH"
    assert row.metrics["win_rate_t5"] == 1.0
    assert row.metrics["avg_return_t5"] == 0.1
    assert row.metrics["avg_excess_t5"] == 0.09

    analyst_sector = summarize_recommendation_backtests(
        config,
        start_time=datetime.fromisoformat("2026-04-29T00:00:00"),
        end_time=datetime.fromisoformat("2026-05-09T00:00:00"),
        group_by="analyst_sector",
    )
    assert analyst_sector.row_count == 1
    analyst_sector_row = analyst_sector.rows[0]
    assert analyst_sector_row.source_candidate is None
    assert analyst_sector_row.analyst_display_name == "张三-分析师"
    assert analyst_sector_row.sector_anchor_type == "industry"
    assert analyst_sector_row.sector_name == "白酒"

    personal_summary = summarize_recommendation_backtests(
        config,
        start_time=datetime.fromisoformat("2026-04-29T00:00:00"),
        end_time=datetime.fromisoformat("2026-05-09T00:00:00"),
        group_by="analyst_sector",
        source="个人消息",
    )
    assert personal_summary.row_count == 0

    conn = connect(config.database_path)
    try:
        alias = conn.execute("SELECT display_name FROM analysts").fetchone()
        assert alias[0] == "张三-分析师"
    finally:
        conn.close()

    rerun = refresh_recommendation_backtests(
        config,
        as_of=date(2026, 5, 8),
        window_days=10,
        windows=[1, 2, 3, 5],
        extractor_version="test-anchor",
    )
    assert rerun.inserted_event_count == 0
    assert rerun.refreshed_count == 0
    assert rerun.skipped_complete_count == 4

    personal_rerun = refresh_recommendation_backtests(
        config,
        as_of=date(2026, 5, 8),
        window_days=10,
        windows=[1, 2, 3, 5],
        source="个人消息",
        extractor_version="test-anchor",
    )
    assert personal_rerun.event_count == 0


def _fake_market_call(config, api_name, params=None, fields=None, *, cache_ttl=None, use_cache=True):
    params = params or {}
    if api_name == "trade_cal":
        start = datetime.strptime(params["start_date"], "%Y%m%d").date()
        end = datetime.strptime(params["end_date"], "%Y%m%d").date()
        days = (end - start).days + 1
        return [
            {"cal_date": (start + timedelta(days=offset)).strftime("%Y%m%d"), "is_open": 1}
            for offset in range(days)
        ]
    if api_name == "daily":
        prices = {
            "20260501": 100,
            "20260502": 103,
            "20260503": 104,
            "20260504": 105,
            "20260505": 106,
            "20260506": 110,
        }
        return _price_rows(params, prices)
    if api_name == "index_daily":
        prices = {
            "20260501": 100,
            "20260502": 100.2,
            "20260503": 100.3,
            "20260504": 100.5,
            "20260505": 100.8,
            "20260506": 101,
        }
        return _price_rows(params, prices)
    raise AssertionError(api_name)


def _price_rows(params, prices):
    start = params["start_date"]
    end = params["end_date"]
    return [
        {"ts_code": params["ts_code"], "trade_date": trade_date, "close": close}
        for trade_date, close in prices.items()
        if start <= trade_date <= end
    ]


def _seed_messages(config: RadarConfig, messages: list[RawMessage]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
    finally:
        conn.close()


def _seed_classifications(config: RadarConfig, classifications: list[MessageClassification]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_message_classifications(conn, classifications)
    finally:
        conn.close()


def _seed_anchors(config: RadarConfig, anchors_by_message: dict[str, list[MessageAnchor]]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        for message_id, anchors in anchors_by_message.items():
            replace_message_anchors(
                conn,
                message_ids=[message_id],
                anchors=anchors,
                trade_date="20260501",
                extractor_version="test-anchor",
            )
    finally:
        conn.close()


def _message(message_id: str, message_time: str, content: str, *, sender: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=sender,
        group_name="投研群",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        fetch_time=datetime.fromisoformat("2026-05-01T12:00:00"),
        fetch_window="2026-05-01",
    )


def _classification(message_id: str, category: str, confidence: float) -> MessageClassification:
    now = datetime.fromisoformat("2026-05-01T12:00:00")
    return MessageClassification(
        message_id=message_id,
        category=category,
        confidence=confidence,
        reason="测试分类",
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _anchor(
    message_id: str,
    anchor_id: str,
    anchor_type: str,
    name: str,
    confidence: float,
) -> MessageAnchor:
    now = datetime.fromisoformat("2026-05-01T12:00:00")
    return MessageAnchor(
        message_id=message_id,
        anchor_id=anchor_id,
        anchor_type=anchor_type,
        name=name,
        confidence=confidence,
        evidence=[{"text": name, "match_type": "exact"}],
        extractor_version="test-anchor",
        trade_date="20260501",
        created_at=now,
        updated_at=now,
    )
