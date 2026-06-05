from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.organize import (
    OrganizeClassificationFilters,
    OrganizeEvidenceFilters,
    list_classification_clusters,
    list_classification_evidence,
)
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages


def test_list_classification_clusters_groups_with_evidence(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "玻璃基板研究观点"),
        _message("m2", "2026-06-04T10:05:00", "电话会报名"),
        _message("m3", "2026-06-04T10:10:00", "继续推荐玻璃基板"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "event", 0.88, "会议通知"),
            _classification(messages[2], "tool_ad", 0.60, "历史工具分类", status="needs_review"),
        ],
    )

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters(keyword="玻璃", evidence_limit=5))
    finally:
        conn.close()

    assert page.summary.classified_count == 2
    assert page.summary.total_count == 1
    assert page.summary.cluster_count == 1
    assert page.summary.low_confidence_count == 1
    assert page.summary.hidden_count == 1
    assert page.clusters[0].category == "research"
    assert page.clusters[0].label == "研究观点"
    assert page.clusters[0].count == 1
    assert [item.message_id for item in page.clusters[0].evidence] == ["m1"]
    assert page.clusters[0].evidence[0].category == "research"


def test_list_classification_clusters_can_skip_evidence(tmp_path):
    config = _config(tmp_path)
    message = _message("m1", "2026-06-04T10:00:00", "玻璃基板研究观点")
    _seed(config, [message])
    _seed_classifications(config, [_classification(message, "research", 0.90, "研究观点")])

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters(evidence_limit=0))
    finally:
        conn.close()

    assert page.summary.total_count == 1
    assert page.clusters[0].count == 1
    assert page.clusters[0].evidence == []


def test_list_classification_clusters_orders_by_value_and_hides_low_value_rows(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "研究观点"),
        _message("m2", "2026-06-04T10:01:00", "会议报名"),
        _message("m3", "2026-06-04T10:02:00", "继续重点推荐"),
        _message("m4", "2026-06-04T10:03:00", "信息残缺"),
        _message("m5", "2026-06-04T10:04:00", "产能变化"),
        _message("m6", "2026-06-04T10:05:00", "收到"),
        _message("m7", "2026-06-04T10:06:00", "低置信研究"),
        _message("m8", "2026-06-04T10:07:00", "基本确定研究"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
            [
                _classification(messages[0], "research", 0.90, "研究观点"),
                _classification(messages[1], "event", 0.90, "会议活动"),
                _classification(messages[2], "recommendation", 0.90, "投资推荐"),
                _classification(messages[3], "unknown", 0.40, "信息不足", status="needs_review"),
                _classification(messages[4], "industry", 0.90, "产业变化"),
                _classification(messages[5], "chat", 0.90, "闲聊", status="ignored"),
                _classification(messages[6], "research", 0.50, "低置信", status="needs_review"),
                _classification(messages[7], "research", 0.70, "基本确定"),
            ],
        )

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters())
        hidden = list_classification_clusters(conn, OrganizeClassificationFilters(category="unknown"))
    finally:
        conn.close()

    assert page.summary.classified_count == 8
    assert page.summary.total_count == 4
    assert page.summary.cluster_count == 4
    assert page.summary.low_confidence_count == 3
    assert page.summary.noise_count == 1
    assert page.summary.hidden_count == 4
    assert [cluster.category for cluster in page.clusters] == ["recommendation", "research", "industry", "event"]
    assert [cluster.low_confidence_count for cluster in page.clusters] == [0, 0, 0, 0]
    assert hidden.summary.classified_count == 1
    assert hidden.summary.total_count == 0
    assert hidden.summary.low_confidence_count == 1
    assert hidden.clusters == []


def test_list_classification_evidence_pages_by_time_and_message_id(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "第一条研究"),
        _message("m2", "2026-06-04T10:01:00", "第二条研究"),
        _message("m3", "2026-06-04T10:02:00", "第三条研究"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "research", 0.90, "研究观点"),
            _classification(messages[2], "research", 0.90, "研究观点"),
        ],
    )

    conn = connect(config.database_path)
    try:
        first = list_classification_evidence(conn, OrganizeEvidenceFilters(category="research", limit=2))
        second = list_classification_evidence(
            conn,
            OrganizeEvidenceFilters(
                category="research",
                limit=2,
                cursor_time=first.next_cursor_time,
                cursor_id=first.next_cursor_id,
            ),
        )
    finally:
        conn.close()

    assert [item.message_id for item in first.items] == ["m3", "m2"]
    assert first.next_cursor_id == "m2"
    assert [item.message_id for item in second.items] == ["m1"]
    assert second.next_cursor_id is None


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})


def _seed(config: RadarConfig, messages: list[RawMessage]) -> None:
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
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name="测试群",
        fetch_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        fetch_window="20260604100000-20260604110000",
    )


def _classification(
    message: RawMessage,
    category: str,
    confidence: float,
    reason: str,
    *,
    status: str = "auto",
) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status=status,
        classifier_type="llm",
        llm_provider="test-provider",
        prompt_version="test",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )
