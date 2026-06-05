from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import MessageAnchor, MessageClassification, RawMessage
from radar.core.store import connect, init_db, replace_message_anchors, upsert_message_classifications, upsert_messages
from radar.web.server.app import create_app


def test_messages_overview_endpoint_returns_anchor_heat(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00"),
        _message("m2", "2026-06-04T09:00:00"),
        _message("m3", "2026-05-20T09:00:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.90, "研究观点"),
                _classification(messages[1], "chat", 0.90, "闲聊"),
                _classification(messages[2], "research", 0.90, "旧研究"),
            ],
        )
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[
                _anchor(messages[0], name="人形机器人"),
                _anchor(messages[1], name="人形机器人"),
                _anchor(messages[2], name="旧主题"),
            ],
            trade_date="20260604",
            extractor_version="test-anchor",
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/messages/overview", params={"days": 2, "anchor_limit": 5})

    assert response.status_code == 200
    assert response.json()["anchor_heat"] == [
        {
            "name": "人形机器人",
            "anchor_type": "concept",
            "mention_count": 2,
            "message_count": 2,
            "high_value_count": 1,
            "average_confidence": 0.8,
            "latest_message_time": "2026-06-04T10:00:00",
        }
    ]


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _message(message_id: str, message_time: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content="人形机器人观点",
        group_name="东财策略",
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )


def _classification(message: RawMessage, category: str, confidence: float, reason: str) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _anchor(message: RawMessage, *, name: str) -> MessageAnchor:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageAnchor(
        message_id=message.message_id,
        anchor_id=f"concept:{name}",
        anchor_type="concept",
        name=name,
        confidence=0.8,
        evidence=[],
        extractor_version="test-anchor",
        trade_date="20260604",
        created_at=now,
        updated_at=now,
    )
