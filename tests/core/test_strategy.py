from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.models import MessageAnchor, MessageClassification, RawMessage
from radar.core.store import connect, init_db, replace_message_anchors, upsert_message_classifications, upsert_messages
from radar.core.usecases.strategy import build_strategy_dashboard


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
    assert stock.first_seen_time == datetime.fromisoformat("2026-06-01T10:00:00")
    assert stock.price_return_since_first_seen == 0.3
    assert stock.signal_age_days == 4
    assert "首现后 +30.0%" in (stock.lifecycle_reason or "")

    candidate = dashboard.stock_candidates[0]
    assert candidate.stock_name == "风华高科"
    assert candidate.lifecycle_state == "已兑现"
    assert candidate.price_return_since_first_seen == 0.3


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
            f"source-{index}",
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


def _insert_daily_close(conn, ts_code: str, trade_date: str, close: float) -> None:
    conn.execute(
        """
        INSERT INTO tushare_history (api_name, ts_code, date_key, data)
        VALUES ('daily', ?, ?, ?)
        """,
        (ts_code, trade_date, json.dumps({"ts_code": ts_code, "trade_date": trade_date, "close": close})),
    )
    conn.commit()
