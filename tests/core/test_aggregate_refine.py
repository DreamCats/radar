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
from radar.core.usecases.aggregation import RefinedTheme, RefinedThemeStock, refine_aggregate_topics
from radar.core.usecases.aggregation.refine import _merge_themes
from radar.core.usecases.aggregation.refine_llm import _normalize_themes


def test_refine_aggregate_topics_uses_work_pool_and_incremental_cache(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "玻璃基板继续发酵"),
            _message("m2", "2026-06-04T10:10:00", "玻璃基板设备更新"),
            _message("m3", "2026-06-04T10:20:00", "光模块订单更新"),
            _message("m4", "2026-06-04T10:30:00", "光模块景气延续"),
        ],
    )
    _seed_classifications(
        config,
        [
            _classification("m1"),
            _classification("m2"),
            _classification("m3"),
            _classification("m4"),
        ],
    )
    _seed_anchors(
        config,
        {
            "m1": [_anchor("m1", "topic:glass", "concept", "玻璃基板", 0.92)],
            "m2": [_anchor("m2", "topic:glass", "concept", "玻璃基板", 0.92)],
            "m3": [_anchor("m3", "topic:optical", "concept", "光模块", 0.92)],
            "m4": [_anchor("m4", "topic:optical", "concept", "光模块", 0.92)],
        },
    )
    calls: list[tuple[str | None, list[str]]] = []

    def fake_refiner(_config, batch, provider_name):
        calls.append((provider_name, [item["candidate_id"] for item in batch]))
        return [
            RefinedTheme(
                theme_name=f"{item['local_name']}投资线索",
                summary=str(item["local_name"]),
                confidence=0.8,
                actionability_score=80,
                related_stocks=[RefinedThemeStock(name="测试股票", confidence=0.7)],
                evidence_message_ids=[item["evidence"][0]["message_id"]],
                merge_from_candidate_ids=[item["candidate_id"]],
            )
            for item in batch
        ]

    result = refine_aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        candidate_limit=2,
        batch_size=1,
        max_concurrency=2,
        provider_names=["p1", "p2"],
        llm_batch_refiner=fake_refiner,
    )

    assert result.status == "succeeded"
    assert result.candidate_count == 2
    assert result.theme_count == 2
    assert result.max_concurrency == 2
    assert {provider for provider, _items in calls} == {"p1", "p2"}

    cached = refine_aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        candidate_limit=2,
        batch_size=1,
        max_concurrency=2,
        provider_names=["p1", "p2"],
        llm_batch_refiner=fake_refiner,
    )

    assert cached.status == "skipped"
    assert cached.input_hash == result.input_hash
    assert len(calls) == 2

    forced = refine_aggregate_topics(
        config,
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
        candidate_limit=2,
        batch_size=1,
        max_concurrency=2,
        provider_names=["p1", "p2"],
        force=True,
        llm_batch_refiner=fake_refiner,
    )

    assert forced.status == "succeeded"
    assert forced.input_hash == result.input_hash
    assert len(calls) == 4


def test_refine_aggregate_topics_allows_empty_candidates_without_llm_config(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})

    result = refine_aggregate_topics(
        config,
        trade_date="20260604",
        start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-05T00:00:00"),
    )

    assert result.status == "succeeded"
    assert result.candidate_count == 0
    assert result.theme_count == 0
    assert result.max_concurrency == 0


def test_refine_normalizes_actionability_score_and_merges_similar_cross_batch_themes():
    themes = _normalize_themes(
        [
            {
                "theme_name": "AI算力硬件及半导体产业链",
                "actionability_score": 8,
                "confidence": 0.8,
                "evidence_message_ids": ["m1", "m2"],
                "merge_from_candidate_ids": ["c1"],
            },
            {
                "theme_name": "AI算力硬件及先进封装产业链",
                "actionability_score": 7,
                "confidence": 0.8,
                "evidence_message_ids": ["m1", "m3"],
                "merge_from_candidate_ids": ["c2"],
            },
        ],
        allowed_candidate_ids={"c1", "c2"},
        allowed_message_ids={"m1", "m2", "m3"},
    )

    merged = _merge_themes(themes)

    assert len(merged) == 1
    assert merged[0].actionability_score == 80
    assert merged[0].evidence_message_ids == ["m1", "m2", "m3"]
    assert merged[0].merge_from_candidate_ids == ["c1", "c2"]


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


def _classification(message_id: str) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message_id,
        category="research",
        confidence=0.90,
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
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageAnchor(
        message_id=message_id,
        anchor_id=anchor_id,
        anchor_type=anchor_type,
        name=name,
        confidence=confidence,
        evidence=[{"text": name, "match_type": "exact", "start": 0}],
        extractor_version="test-anchor",
        trade_date="20260604",
        created_at=now,
        updated_at=now,
    )
