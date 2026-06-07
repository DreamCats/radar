from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.models import MessageAnchor, MessageClassification, RawMessage
from radar.core.store import connect, init_db, replace_message_anchors, upsert_message_classifications, upsert_messages
from radar.core.usecases.strategy import build_strategy_dashboard
from radar.core.usecases.strategy.snapshots import (
    StrategySnapshotSaveResult,
    backfill_strategy_snapshot_returns,
    save_strategy_snapshot,
    summarize_strategy_validation,
)
from radar.core.usecases.strategy.snapshot_cache import save_cached_strategy_snapshot


def test_build_strategy_dashboard_ranks_anchor_breakout(tmp_path: Path):
    config = _config(tmp_path)
    recent_messages = [
        _message("m1", "2026-06-07T10:00:00", "涨价 订单 MLCC"),
        _message("m2", "2026-06-06T10:00:00", "扩产 算力 MLCC"),
        _message("m3", "2026-06-05T10:00:00", "业绩 放量 MLCC"),
    ]
    old_message = _message("m0", "2026-05-20T10:00:00", "MLCC 旧观点")
    messages = [old_message, *recent_messages]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [_classification(message, "recommendation", 0.9) for message in recent_messages]
            + [_classification(old_message, "research", 0.9)],
        )
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260607",
            extractor_version="test-anchor",
        )
    finally:
        conn.close()

    dashboard = build_strategy_dashboard(config, days=30, recent_days=7, limit=5)

    assert dashboard.opportunities[0].name == "MLCC"
    assert dashboard.opportunities[0].recent_message_count == 3
    assert "涨价" in dashboard.opportunities[0].catalyst_terms


def test_strategy_uses_full_anchor_backtest_instead_of_selected_stocks(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message(f"m{i}", f"2026-06-0{i}T10:00:00", f"MLCC 涨价 订单 stock{i}")
        for i in range(1, 7)
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.9) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260607",
            extractor_version="test-anchor",
        )
        for index, message in enumerate(messages, start=1):
            excess_return = 0.2 if index <= 5 else -0.4
            _insert_backtest_event(conn, message, index=index, excess_return=excess_return)
    finally:
        conn.close()

    dashboard = build_strategy_dashboard(config, days=30, recent_days=7, limit=5)
    opportunity = dashboard.opportunities[0]

    assert opportunity.name == "MLCC"
    assert opportunity.opportunity_backtest.matured_event_count == 6
    assert opportunity.opportunity_backtest.average_excess_return_t5 == 0.1
    assert opportunity.average_excess_return_t5 == 0.1
    assert opportunity.selected_stock_backtest.matured_event_count == 5
    assert opportunity.selected_stock_backtest.average_excess_return_t5 == 0.2


def test_strategy_marks_related_stock_lifecycle_from_market_prices(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T10:00:00", "MLCC 风华高科 涨价"),
        _message("m2", "2026-06-02T10:00:00", "MLCC 风华高科 订单"),
        _message("m3", "2026-06-05T10:00:00", "MLCC 风华高科 放量"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.9) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260605",
            extractor_version="test-anchor",
        )
        for index, message in enumerate(messages, start=1):
            _insert_backtest_event(
                conn,
                message,
                index=index,
                excess_return=0.1,
                stock_name="风华高科",
                ts_code="000636.SZ",
            )
    finally:
        conn.close()

    market_conn = connect(config.market_database_path)
    try:
        migrate_market_db(market_conn)
        _insert_daily_close(market_conn, "000636.SZ", "20260601", 10)
        _insert_daily_close(market_conn, "000636.SZ", "20260602", 11)
        _insert_daily_close(market_conn, "000636.SZ", "20260603", 12)
        _insert_daily_close(market_conn, "000636.SZ", "20260604", 13)
        _insert_daily_close(market_conn, "000636.SZ", "20260605", 13)
    finally:
        market_conn.close()

    dashboard = build_strategy_dashboard(config, days=30, recent_days=7, limit=5)
    stock = dashboard.opportunities[0].related_stocks[0]

    assert stock.stock_name == "风华高科"
    assert stock.lifecycle_state == "已兑现"
    assert stock.decision_bucket == "已兑现复盘"
    assert stock.price_position == "趋势健康"
    assert stock.first_seen_time == datetime.fromisoformat("2026-06-01T10:00:00")
    assert stock.price_return_since_first_seen == 0.3
    assert stock.signal_age_days == 4
    assert "首现后 +30.0%" in (stock.lifecycle_reason or "")

    candidate = dashboard.stock_candidates[0]
    assert candidate.stock_name == "风华高科"
    assert candidate.lifecycle_state == "已兑现"
    assert candidate.decision_bucket == "已兑现复盘"
    assert candidate.price_position == "趋势健康"
    assert candidate.price_return_since_first_seen == 0.3


def test_strategy_marks_fermenting_stock_price_position(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T10:00:00", "MLCC 中天科技 订单"),
        _message("m2", "2026-06-02T10:00:00", "MLCC 中天科技 放量"),
        _message("m3", "2026-06-05T10:00:00", "MLCC 中天科技 涨价"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.9) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260605",
            extractor_version="test-anchor",
        )
        for index, message in enumerate(messages, start=1):
            _insert_backtest_event(
                conn,
                message,
                index=index,
                excess_return=0.08,
                stock_name="中天科技",
                ts_code="600522.SH",
            )
    finally:
        conn.close()

    market_conn = connect(config.market_database_path)
    try:
        migrate_market_db(market_conn)
        _insert_daily_close(market_conn, "600522.SH", "20260601", 10)
        _insert_daily_close(market_conn, "600522.SH", "20260602", 10.5)
        _insert_daily_close(market_conn, "600522.SH", "20260603", 10.8)
        _insert_daily_close(market_conn, "600522.SH", "20260604", 11.0)
        _insert_daily_close(market_conn, "600522.SH", "20260605", 11.2)
    finally:
        market_conn.close()

    dashboard = build_strategy_dashboard(config, days=30, recent_days=7, limit=5)
    stock = dashboard.opportunities[0].related_stocks[0]

    assert stock.stock_name == "中天科技"
    assert stock.lifecycle_state == "发酵中"
    assert stock.price_position == "趋势健康"
    assert stock.price_return_since_first_seen == 0.12


def test_strategy_scores_event_credibility_from_first_event(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T10:00:00", "MLCC 涨价 订单 扩产 客户突破 商络电子"),
        _message("m2", "2026-06-02T10:00:00", "MLCC 放量 供不应求 商络电子"),
        _message("m3", "2026-06-05T10:00:00", "MLCC 业绩 预期差 商络电子"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.9) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260605",
            extractor_version="test-anchor",
        )
        for index, message in enumerate(messages, start=1):
            _insert_backtest_event(
                conn,
                message,
                index=index,
                excess_return=0.08,
                stock_name="商络电子",
                ts_code="300975.SZ",
                source_name="强逻辑来源",
            )
    finally:
        conn.close()

    market_conn = connect(config.market_database_path)
    try:
        migrate_market_db(market_conn)
        _insert_daily_close(market_conn, "300975.SZ", "20260601", 10)
        _insert_daily_close(market_conn, "300975.SZ", "20260602", 10.4)
        _insert_daily_close(market_conn, "300975.SZ", "20260603", 10.7)
        _insert_daily_close(market_conn, "300975.SZ", "20260604", 10.9)
        _insert_daily_close(market_conn, "300975.SZ", "20260605", 11.2)
    finally:
        market_conn.close()

    dashboard = build_strategy_dashboard(config, days=30, recent_days=7, limit=5)
    stock = dashboard.opportunities[0].related_stocks[0]

    assert stock.stock_name == "商络电子"
    assert stock.realtime_score >= 60
    assert stock.decision_bucket == "今日可关注"
    assert stock.event_credibility is not None
    assert stock.event_credibility.level == "中可信"
    assert stock.event_credibility.first_source_name == "强逻辑来源"
    assert stock.event_credibility.logic_hit_count >= 4
    assert "来源成熟样本不足" in stock.event_credibility.risks

    candidate = dashboard.stock_candidates[0]
    assert candidate.event_credibility is not None
    assert candidate.event_credibility.first_source_name == "强逻辑来源"


def test_strategy_snapshot_persists_and_backfills_returns(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-05T10:00:00", "MLCC 订单 扩产 厦门钨业"),
        _message("m2", "2026-06-04T10:00:00", "MLCC 涨价 厦门钨业"),
        _message("m3", "2026-06-03T10:00:00", "MLCC 放量 厦门钨业"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.9) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "MLCC") for message in messages],
            trade_date="20260605",
            extractor_version="test-anchor",
        )
        for index, message in enumerate(messages, start=1):
            _insert_backtest_event(
                conn,
                message,
                index=index,
                excess_return=0.08,
                stock_name="厦门钨业",
                ts_code="600549.SH",
                source_name="高可信来源",
            )
    finally:
        conn.close()

    market_conn = connect(config.market_database_path)
    try:
        migrate_market_db(market_conn)
        for offset, close in enumerate([10, 10.5, 11, 12], start=5):
            _insert_daily_close(market_conn, "600549.SH", f"2026060{offset}", close)
            _insert_daily_close(market_conn, "000300.SH", f"2026060{offset}", 100 + offset, api_name="index_daily")
    finally:
        market_conn.close()

    saved = save_strategy_snapshot(config, days=30, recent_days=7, limit=5)
    backfilled = backfill_strategy_snapshot_returns(config, windows=[3], snapshot_id=saved.snapshot_id)

    assert saved.stock_count == 1
    assert backfilled.refreshed_count == 1

    conn = connect(config.database_path)
    try:
        stock_row = conn.execute(
            "SELECT decision_bucket, stock_name FROM strategy_snapshot_stocks WHERE snapshot_id = ?",
            (saved.snapshot_id,),
        ).fetchone()
        return_row = conn.execute(
            """
            SELECT status, return_rate, excess_return_rate, max_drawdown_rate
            FROM strategy_snapshot_returns
            WHERE snapshot_id = ? AND ts_code = '600549.SH' AND window_days = 3
            """,
            (saved.snapshot_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO strategy_snapshots (
                snapshot_id, strategy_type, start_time, end_time, recent_start_time,
                generated_at, created_at, opportunity_count, stock_count, payload_json
            ) VALUES (
                'other-snap', 'early_concept_radar', '2026-06-01T10:00:00', '2026-06-05T10:00:00',
                '2026-06-04T10:00:00', '2026-06-05T10:00:00', '2026-06-05T10:00:00',
                1, 1, '{}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_snapshot_stocks (
                snapshot_id, ts_code, stock_name, rank, decision_bucket, decision_reason,
                realtime_score, credibility_level, lifecycle_state, price_position,
                first_seen_time, latest_message_time, event_count, source_count,
                win_rate_t5, average_excess_return_t5, first_source_name, payload_json
            ) VALUES (
                'other-snap', '000001.SZ', '混入口径', 1, '混入口径', NULL,
                99, '高可信', NULL, NULL, '2026-06-05T10:00:00', '2026-06-05T10:00:00',
                1, 1, NULL, NULL, '混入来源', '{}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_snapshot_returns (
                snapshot_id, ts_code, window_days, benchmark_ts_code, base_trade_date,
                target_trade_date, base_close, target_close, return_rate,
                benchmark_return_rate, excess_return_rate, max_drawdown_rate, status,
                error_message, updated_at
            ) VALUES (
                'other-snap', '000001.SZ', 3, '000300.SH', '20260605',
                '20260610', 10, 20, 1.0, 0.0, 1.0, 0.0, 'succeeded',
                NULL, '2026-06-10T10:00:00'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    assert stock_row["stock_name"] == "厦门钨业"
    assert stock_row["decision_bucket"] in {"今日可关注", "观察等待", "已兑现复盘"}
    assert return_row["status"] == "succeeded"
    assert round(return_row["return_rate"], 4) == 0.2
    assert return_row["excess_return_rate"] > 0
    assert return_row["max_drawdown_rate"] == 0

    summary = summarize_strategy_validation(config, window_days=3)
    assert summary.snapshot_count == 1
    assert summary.matured_stock_count == 1
    assert summary.by_decision_bucket[0].sample_count == 1
    assert all(metric.label != "混入口径" for metric in summary.by_decision_bucket)
    assert all(metric.label != "混入来源" for metric in summary.top_sources)
    assert summary.by_decision_bucket[0].average_excess_return is not None

    cached = save_cached_strategy_snapshot(config, days=30, recent_days=7, limit=5)
    assert isinstance(cached, StrategySnapshotSaveResult)
    assert cached.snapshot_id == saved.snapshot_id
    assert cached.reused_existing is True


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _message(message_id: str, message_time: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=f"sender-{message_id}",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name="策略测试群",
        fetch_time=datetime.fromisoformat("2026-06-07T10:01:00"),
        fetch_window="20260607100000-20260607110000",
    )


def _classification(message: RawMessage, category: str, confidence: float) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-07T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason="策略测试",
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _anchor(message: RawMessage, name: str) -> MessageAnchor:
    now = datetime.fromisoformat("2026-06-07T12:00:00")
    return MessageAnchor(
        message_id=message.message_id,
        anchor_id=f"concept:{name}",
        anchor_type="concept",
        name=name,
        confidence=0.9,
        evidence=[],
        extractor_version="test-anchor",
        trade_date="20260607",
        created_at=now,
        updated_at=now,
    )


def _insert_backtest_event(
    conn,
    message: RawMessage,
    *,
    index: int,
    excess_return: float,
    stock_name: str | None = None,
    ts_code: str | None = None,
    source_name: str | None = None,
) -> None:
    now = datetime.fromisoformat("2026-06-07T12:00:00")
    event_id = f"event-{index}"
    conn.execute(
        """
        INSERT INTO recommendation_events (
            event_id, message_id, source, source_candidate, group_name, category,
            classification_confidence, ts_code, stock_name, action, message_time,
            event_date, extractor_version, anchor_confidence, analyst_id,
            analyst_display_name, analyst_alias_key, sector_anchor_id,
            sector_anchor_type, sector_name, sector_confidence, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            message.message_id,
            message.source,
            source_name or f"source-{index}",
            message.group_name,
            "recommendation",
            0.9,
            ts_code or f"00000{index}.SZ",
            stock_name or f"股票{index}",
            "bullish",
            message.message_time.isoformat(),
            message.message_time.strftime("%Y%m%d"),
            "test-event",
            0.9,
            None,
            None,
            None,
            None,
            None,
            "MLCC",
            0.9,
            now.isoformat(),
            now.isoformat(),
        ),
    )
    conn.execute(
        """
        INSERT INTO recommendation_backtest_windows (
            event_id, window_days, benchmark_ts_code, return_rate, win,
            benchmark_return_rate, excess_return_rate, status, updated_at
        ) VALUES (?, 5, '000300.SH', ?, ?, 0, ?, 'succeeded', ?)
        """,
        (event_id, excess_return, int(excess_return > 0), excess_return, now.isoformat()),
    )
    conn.commit()


def _insert_daily_close(conn, ts_code: str, trade_date: str, close: float, *, api_name: str = "daily") -> None:
    conn.execute(
        """
        INSERT INTO tushare_history (api_name, ts_code, date_key, data)
        VALUES (?, ?, ?, ?)
        """,
        (api_name, ts_code, trade_date, json.dumps({"ts_code": ts_code, "trade_date": trade_date, "close": close})),
    )
    conn.commit()
