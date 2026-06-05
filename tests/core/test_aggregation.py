from __future__ import annotations

from datetime import datetime
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
from radar.core.usecases.aggregation import aggregate_topics


def test_aggregate_topics_groups_topic_anchors_with_related_stocks(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "玻璃基板和先进封装继续发酵"),
            _message("m2", "2026-06-04T10:10:00", "玻璃基板推荐继续关注"),
            _message("m3", "2026-06-04T10:20:00", "会议也提到玻璃基板"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research", 0.90),
            _classification("m2", "recommendation", 0.88),
            _classification("m3", "event", 0.95),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [
                _anchor("m1", "topic:glass", "concept", "玻璃基板", 0.92),
                _anchor("m1", "topic:packaging", "concept", "先进封装", 0.88),
                _anchor("m1", "stock:a", "stock", "沃格光电", 0.98),
                _anchor("m1", "stock:b", "stock", "凯盛科技", 0.98),
            ],
            "m2": [
                _anchor("m2", "topic:glass", "concept", "玻璃基板", 0.95),
                _anchor("m2", "stock:a", "stock", "沃格光电", 0.98),
            ],
            "m3": [
                _anchor("m3", "topic:glass", "concept", "玻璃基板", 0.95),
                _anchor("m3", "stock:c", "stock", "精测电子", 0.98),
            ],
        },
    )

    result = aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        min_messages=2,
    )

    assert result.topic_count == 1
    topic = result.topics[0]
    assert topic.name == "玻璃基板"
    assert topic.message_count == 2
    assert topic.category_distribution == {"research": 1, "recommendation": 1}
    assert [(stock.name, stock.count) for stock in topic.related_stocks] == [
        ("沃格光电", 2),
        ("凯盛科技", 1),
    ]
    assert [item.message_id for item in topic.evidence] == ["m2", "m1"]


def test_aggregate_topics_binds_stocks_within_same_segment(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    content = "玻璃基板：沃格光电继续发酵。\nPCB：世运电路有更新。"
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", content),
            _message("m2", "2026-06-04T10:10:00", "玻璃基板：凯盛科技跟进。"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research", 0.90),
            _classification("m2", "research", 0.90),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [
                _anchor("m1", "topic:glass", "concept", "玻璃基板", 0.92, start=content.index("玻璃基板")),
                _anchor("m1", "stock:a", "stock", "沃格光电", 0.98, start=content.index("沃格光电")),
                _anchor("m1", "topic:pcb", "concept", "PCB", 0.92, start=content.index("PCB")),
                _anchor("m1", "stock:b", "stock", "世运电路", 0.98, start=content.index("世运电路")),
            ],
            "m2": [
                _anchor("m2", "topic:glass", "concept", "玻璃基板", 0.92, start=0),
                _anchor("m2", "stock:c", "stock", "凯盛科技", 0.98, start=5),
            ],
        },
    )

    result = aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        min_messages=2,
    )

    topic = result.topics[0]
    assert topic.name == "玻璃基板"
    assert {(stock.name, stock.count) for stock in topic.related_stocks} == {
        ("沃格光电", 1),
        ("凯盛科技", 1),
    }
    assert "世运电路" not in {stock.name for stock in topic.related_stocks}
    assert "PCB" not in {topic.name for topic in result.topics}


def test_aggregate_topics_downweights_generic_topics_covered_by_specific_topics(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "芯片方向，玻璃基板继续发酵"),
            _message("m2", "2026-06-04T10:10:00", "芯片方向，玻璃基板推荐关注"),
            _message("m3", "2026-06-04T10:20:00", "芯片方向，光模块订单更新"),
            _message("m4", "2026-06-04T10:30:00", "芯片方向，光模块景气延续"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research", 0.90),
            _classification("m2", "research", 0.90),
            _classification("m3", "research", 0.90),
            _classification("m4", "research", 0.90),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [
                _anchor("m1", "topic:chip", "concept", "芯片", 0.95),
                _anchor("m1", "topic:glass", "concept", "玻璃基板", 0.94),
            ],
            "m2": [
                _anchor("m2", "topic:chip", "concept", "芯片", 0.95),
                _anchor("m2", "topic:glass", "concept", "玻璃基板", 0.94),
            ],
            "m3": [
                _anchor("m3", "topic:chip", "concept", "芯片", 0.95),
                _anchor("m3", "topic:optical", "concept", "光模块", 0.94),
            ],
            "m4": [
                _anchor("m4", "topic:chip", "concept", "芯片", 0.95),
                _anchor("m4", "topic:optical", "concept", "光模块", 0.94),
            ],
        },
    )

    result = aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        min_messages=2,
    )

    names = [topic.name for topic in result.topics]
    assert names.index("芯片") > names.index("玻璃基板")
    assert names.index("芯片") > names.index("光模块")


def test_aggregate_topics_does_not_bind_stocks_from_dense_list_segments(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    content = "题材合集，光模块/芯片/玻璃基板、沃格光电、凯盛科技，欢迎交流。"
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", content),
            _message("m2", "2026-06-04T10:10:00", "玻璃基板继续发酵。"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1", "research", 0.90),
            _classification("m2", "research", 0.90),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [
                _anchor("m1", "topic:optical", "concept", "光模块", 0.92, start=5),
                _anchor("m1", "topic:chip", "concept", "芯片", 0.92, start=9),
                _anchor("m1", "topic:glass", "concept", "玻璃基板", 0.92, start=12),
                _anchor("m1", "stock:a", "stock", "沃格光电", 0.98, start=17),
                _anchor("m1", "stock:b", "stock", "凯盛科技", 0.98, start=22),
            ],
            "m2": [_anchor("m2", "topic:glass", "concept", "玻璃基板", 0.92, start=0)],
        },
    )

    result = aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        min_messages=2,
    )

    topic = result.topics[0]
    assert topic.name == "玻璃基板"
    assert topic.related_stocks == []
    assert topic.evidence[0].stocks == []


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
                trade_date="20260604",
                extractor_version="test-anchor",
            )
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


def _classification(message_id: str, category: str, confidence: float) -> MessageClassification:
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


def _anchor(
    message_id: str,
    anchor_id: str,
    anchor_type: str,
    name: str,
    confidence: float,
    *,
    start: int | None = None,
) -> MessageAnchor:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    evidence = {"text": name, "match_type": "exact"}
    if start is not None:
        evidence["start"] = start
    return MessageAnchor(
        message_id=message_id,
        anchor_id=anchor_id,
        anchor_type=anchor_type,
        name=name,
        confidence=confidence,
        evidence=[evidence],
        extractor_version="test-anchor",
        trade_date="20260604",
        created_at=now,
        updated_at=now,
    )
