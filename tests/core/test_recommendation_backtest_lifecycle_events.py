from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases.recommendation_backtest.events import (
    RECOMMENDATION_EVENT_EXTRACTOR_VERSION,
    refresh_recommendation_events,
)
from radar.core.usecases.recommendation_backtest.summary import summarize_recommendation_backtests


def test_refresh_recommendation_events_uses_lifecycle_evidence(tmp_path: Path):
    config = _config(tmp_path)
    message = _message("m1", "2026-06-09T09:30:00", "张三", "个人群", "继续推荐顺络电子，涨价和订单逻辑强化")
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [message])
        upsert_message_classifications(conn, [_classification(message, "recommendation", 0.91)])
        _insert_lifecycle_judgement(
            conn,
            as_of=datetime.fromisoformat("2026-06-09T15:00:00"),
            ts_code="002138.SZ",
            stock_name="顺络电子",
            message_id=message.message_id,
            evidence_type="报告",
            confidence=0.84,
        )

        events, inserted = refresh_recommendation_events(
            config,
            conn,
            start_time=datetime.fromisoformat("2026-06-09T00:00:00"),
            end_time=datetime.fromisoformat("2026-06-10T00:00:00"),
        )

        assert inserted == 1
        assert len(events) == 1
        event = events[0]
        assert event.extractor_version == RECOMMENDATION_EVENT_EXTRACTOR_VERSION
        assert event.message_id == "m1"
        assert event.ts_code == "002138.SZ"
        assert event.stock_name == "顺络电子"
        assert event.source_candidate == "张三"
        assert event.action == "bullish"
        assert event.anchor_confidence > 0.7

        events, inserted = refresh_recommendation_events(
            config,
            conn,
            start_time=datetime.fromisoformat("2026-06-09T00:00:00"),
            end_time=datetime.fromisoformat("2026-06-10T00:00:00"),
        )
        assert inserted == 0
        assert len(events) == 1
    finally:
        conn.close()


def test_summary_ignores_legacy_anchor_events(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("new", "2026-06-09T09:30:00", "张三", "个人群", "继续推荐顺络电子"),
        _message("old", "2026-06-09T10:30:00", "李四", "个人群", "旧推荐事件"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        _insert_event(conn, "new-event", "new", "张三", RECOMMENDATION_EVENT_EXTRACTOR_VERSION)
        _insert_event(conn, "old-event", "old", "李四", "market-anchor-v1")
        _insert_window(conn, "new-event", 5, return_rate=0.08)
        _insert_window(conn, "old-event", 5, return_rate=0.30)
    finally:
        conn.close()

    result = summarize_recommendation_backtests(
        config,
        start_time=datetime.fromisoformat("2026-06-09T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-10T00:00:00"),
        group_by="source",
        windows=[5],
        min_count=1,
        limit=10,
    )

    assert result.row_count == 1
    assert result.rows[0].source_candidate == "张三"
    assert result.rows[0].metrics["avg_return_t5"] == 0.08


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _message(message_id: str, message_time: str, sender: str, source: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        fetch_time=datetime.fromisoformat("2026-06-09T09:35:00"),
        fetch_window="20260609090000-20260609100000",
        group_name="强逻辑群" if source == "个人群" else None,
    )


def _classification(message: RawMessage, category: str, confidence: float) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-09T09:40:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason="测试分类",
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _insert_lifecycle_judgement(
    conn,
    *,
    as_of: datetime,
    ts_code: str,
    stock_name: str,
    message_id: str,
    evidence_type: str,
    confidence: float,
) -> None:
    window_start = datetime.fromisoformat("2026-06-08T15:00:00")
    evidence_start = datetime.fromisoformat("2026-05-01T00:00:00")
    result = {
        "stage_code": "seed",
        "stage_label": "种子期",
        "confidence": confidence,
        "one_line": "测试生命周期判断",
        "why": ["测试证据"],
        "evidence_chain": [
            {
                "time": "2026-06-09 09:30",
                "type": evidence_type,
                "evidence": "继续推荐，逻辑强化",
                "message_id": message_id,
            }
        ],
    }
    refs = [{"message_id": message_id, "message_time": "2026-06-09T09:30:00", "sender": "张三", "group_name": "强逻辑群"}]
    conn.execute(
        """
        INSERT INTO stock_lifecycle_judgements (
            judgement_id, as_of_time, window_start_time, evidence_start_time, ts_code,
            stock_name, stage, confidence, trigger_count, unique_trigger_count,
            sender_count, conversation_count, evidence_count, channels_json,
            evidence_refs_json, llm_provider, model, prompt_version,
            result_json, created_at, updated_at, evidence_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            as_of.isoformat(),
            window_start.isoformat(),
            evidence_start.isoformat(),
            ts_code,
            stock_name,
            "seed",
            confidence,
            3,
            3,
            2,
            2,
            1,
            "[]",
            json.dumps(refs, ensure_ascii=False),
            "test",
            "test",
            "test",
            json.dumps(result, ensure_ascii=False),
            as_of.isoformat(),
            as_of.isoformat(),
            "sig",
        ),
    )
    conn.commit()


def _insert_event(conn, event_id: str, message_id: str, sender: str, extractor_version: str) -> None:
    now = "2026-06-09T12:00:00"
    conn.execute(
        """
        INSERT INTO recommendation_events (
            event_id, message_id, source, source_candidate, group_name, category,
            classification_confidence, ts_code, stock_name, action, message_time,
            event_date, extractor_version, anchor_confidence, created_at, updated_at,
            analyst_id, analyst_display_name, analyst_alias_key, sector_anchor_id,
            sector_anchor_type, sector_name, sector_confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            message_id,
            "个人群",
            sender,
            "强逻辑群",
            "recommendation",
            0.9,
            "002138.SZ",
            "顺络电子",
            "bullish",
            "2026-06-09T09:30:00",
            "20260609",
            extractor_version,
            0.86,
            now,
            now,
            f"an_{sender}",
            sender,
            sender,
            None,
            None,
            None,
            None,
        ),
    )
    conn.commit()


def _insert_window(conn, event_id: str, window: int, *, return_rate: float) -> None:
    conn.execute(
        """
        INSERT INTO recommendation_backtest_windows (
            event_id, window_days, benchmark_ts_code, base_trade_date, target_trade_date,
            base_close, target_close, return_rate, win, benchmark_base_close,
            benchmark_target_close, benchmark_return_rate, excess_return_rate,
            status, error_message, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            window,
            "000300.SH",
            "20260609",
            "20260616",
            10,
            10 * (1 + return_rate),
            return_rate,
            1,
            100,
            101,
            0.01,
            return_rate - 0.01,
            "succeeded",
            None,
            "2026-06-16T15:00:00",
        ),
    )
    conn.commit()
