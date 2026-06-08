from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.market_anchors import refresh_market_anchors
from radar.core.models import MessageClassification, RawMessage
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases.anchoring import anchor_messages_range, extract_message_anchors, load_anchor_dictionary
from radar.core.usecases.anchoring.dictionary import AnchorDictionary, AnchorTerm


def test_anchor_messages_range_extracts_and_skips_processed_messages(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "寒武纪今天继续强，算力这条线还在发酵"),
            _message("m2", "2026-06-04T10:01:00", "周末聚餐别忘了报名"),
            _message("m3", "2026-06-04T10:02:00", "闲聊消息"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research"),
            _classification("m2", "research"),
            _classification("m3", "chat"),
        ],
    )

    result = anchor_messages_range(
        config,
        trade_date="20260604",
        category="research",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        limit=2,
    )

    assert result.scanned_count == 2
    assert result.anchored_message_count == 1
    assert result.anchor_count >= 2
    assert result.type_distribution["stock"] == 1
    assert result.top_anchors["寒武纪"] == 1
    assert result.top_anchors["算力"] == 1

    with sqlite3.connect(tmp_path / "radar.sqlite3") as conn:
        anchors = conn.execute(
            """
            SELECT message_id, anchor_type, name
            FROM message_anchors
            ORDER BY message_id, anchor_type, name
            """
        ).fetchall()
        statuses = conn.execute(
            """
            SELECT message_id, trade_date, anchor_count
            FROM message_anchor_status
            ORDER BY message_id
            """
        ).fetchall()
    assert ("m1", "stock", "寒武纪") in anchors
    assert ("m1", "concept", "算力") in anchors
    assert statuses == [("m1", "20260604", result.anchor_count), ("m2", "20260604", 0)]

    skipped = anchor_messages_range(
        config,
        trade_date="20260604",
        category="research",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert skipped.scanned_count == 0
    assert skipped.anchor_count == 0


def test_anchor_messages_range_reprocesses_for_different_trade_date(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config, trade_date="20260604")
    _seed_market(config, trade_date="20260605")
    _seed_messages(
        config,
        [_message("m1", "2026-06-04T10:00:00", "寒武纪今天继续强，算力这条线还在发酵")],
    )
    _seed_classifications(config, [_classification("m1", "research")])

    first = anchor_messages_range(
        config,
        trade_date="20260604",
        category="research",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )
    second = anchor_messages_range(
        config,
        trade_date="20260605",
        category="research",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert first.scanned_count == 1
    assert second.scanned_count == 1
    with sqlite3.connect(tmp_path / "radar.sqlite3") as conn:
        status_dates = conn.execute(
            """
            SELECT trade_date, anchor_count
            FROM message_anchor_status
            ORDER BY trade_date
            """
        ).fetchall()
    assert status_dates == [("20260604", first.anchor_count), ("20260605", second.anchor_count)]


def test_extract_message_anchors_accepts_reference_segmenter(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config)
    dictionary = load_anchor_dictionary(config, trade_date="20260604")
    message = _message("m1", "2026-06-04T10:00:00", "国产 AI 芯片逻辑继续发酵")

    anchors = extract_message_anchors(message, dictionary, segmenter=lambda _: ["AI芯片"])

    assert any(item.name == "AI芯片" for item in anchors)


def test_extract_message_anchors_does_not_match_ascii_term_inside_word():
    dictionary = AnchorDictionary(
        trade_date="20260604",
        terms=[
            AnchorTerm(
                anchor_id="topic:cro",
                anchor_type="concept",
                name="CRO",
                term="CRO",
                term_kind="name",
                trade_date="20260604",
            ),
            AnchorTerm(
                anchor_id="topic:cpo",
                anchor_type="concept",
                name="CPO",
                term="CPO",
                term_kind="name",
                trade_date="20260604",
            ),
        ],
    )
    message = _message("m1", "2026-06-04T10:00:00", "Micron 有更新，光模块/CPO 继续发酵")

    anchors = extract_message_anchors(message, dictionary)

    assert [item.name for item in anchors] == ["CPO"]


def test_anchor_messages_range_filters_low_confidence_classifications(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "寒武纪和算力继续发酵"),
            _message("m2", "2026-06-04T10:01:00", "芯片消息但分类低置信"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research", confidence=0.90),
            _classification("m2", "research", confidence=0.60),
        ],
    )

    result = anchor_messages_range(
        config,
        trade_date="20260604",
        category="research",
        min_classification_confidence=0.7,
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert result.scanned_count == 1
    assert result.anchored_message_count == 1


def test_anchor_messages_range_defaults_to_investment_categories(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "寒武纪和算力继续发酵"),
            _message("m2", "2026-06-04T10:01:00", "会议提到算力"),
            _message("m3", "2026-06-04T10:02:00", "聊天提到芯片"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research"),
            _classification("m2", "event"),
            _classification("m3", "chat"),
        ],
    )

    result = anchor_messages_range(
        config,
        trade_date="20260604",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert result.categories == ["research", "recommendation", "industry"]
    assert result.scanned_count == 1


def test_anchor_messages_range_excludes_event_when_requested(tmp_path: Path):
    config = _config(tmp_path)
    _seed_market(config)
    _seed_messages(
        config,
        [_message("m1", "2026-06-04T10:00:00", "会议提到算力")],
    )
    _seed_classifications(config, [_classification("m1", "event")])

    result = anchor_messages_range(
        config,
        trade_date="20260604",
        categories=["event"],
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert result.categories == []
    assert result.scanned_count == 0


def _seed_market(config: RadarConfig, *, trade_date: str = "20260604") -> None:
    def fake_call(_config, api_name, _params, _fields):
        rows = {
            "dc_concept": [
                {"theme_code": "000001.DC", "trade_date": trade_date, "name": "算力", "hot": 900},
                {"theme_code": "000002.DC", "trade_date": trade_date, "name": "AI芯片", "hot": 800},
            ],
            "dc_concept_cons": [
                {
                    "ts_code": "688256.SH",
                    "trade_date": trade_date,
                    "name": "寒武纪",
                    "theme_code": "000001.DC",
                    "industry_code": "BK001",
                    "industry": "半导体",
                    "reason": "国产 AI 芯片",
                    "hot_num": 600,
                }
            ],
        }
        return rows.get(api_name, [])

    refresh_market_anchors(config, trade_date=trade_date, tushare_call=fake_call)


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


def _message(message_id: str, message_time: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="sender",
        group_name="投研群",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        fetch_time=datetime.fromisoformat("2026-06-04T12:00:00"),
        fetch_window="2026-06-04",
    )


def _classification(message_id: str, category: str, *, confidence: float = 0.90) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
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


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path},
        market={
            "provider": "tushare",
            "secret_ref": "tushare_main",
            "api_url": "https://example.invalid/tushare",
            "database": tmp_path / "market.sqlite3",
        },
        secrets=RadarSecrets(market={"tushare_main": {"token": "secret-token"}}),
    )
