from __future__ import annotations

from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
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
