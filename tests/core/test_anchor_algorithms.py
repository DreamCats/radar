from __future__ import annotations

from datetime import datetime

from radar.core.algorithms.anchors import AnchorRankingConfig, rank_anchor_batch
from radar.core.models import MessageAnchor


def test_rank_anchor_batch_merges_duplicate_non_stock_names():
    ranked = rank_anchor_batch(
        {
            "m1": [
                _anchor("m1", "concept:glass", "concept", "玻璃基板", 0.90),
                _anchor("m1", "theme:glass", "theme", "玻璃基板", 0.80),
                _anchor("m1", "concept:chip", "concept", "芯片", 0.82),
            ]
        },
        config=AnchorRankingConfig(max_anchors_per_message=6),
    )

    items = ranked["m1"]
    assert [item.name for item in items].count("玻璃基板") == 1
    glass = next(item for item in items if item.name == "玻璃基板")
    assert glass.anchor_type == "concept"
    assert any(item.get("match_type") == "canonical_duplicate" for item in glass.evidence)


def test_rank_anchor_batch_keeps_stock_separate_from_same_name_concept():
    ranked = rank_anchor_batch(
        {
            "m1": [
                _anchor("m1", "stock:300024.SZ", "stock", "机器人", 0.98),
                _anchor("m1", "concept:robot", "concept", "机器人", 0.90),
            ]
        },
        config=AnchorRankingConfig(max_anchors_per_message=6),
    )

    assert {(item.anchor_type, item.name) for item in ranked["m1"]} == {
        ("stock", "机器人"),
        ("concept", "机器人"),
    }


def test_rank_anchor_batch_limits_to_primary_anchors():
    ranked = rank_anchor_batch(
        {
            "m1": [
                _anchor("m1", "stock:688256.SH", "stock", "寒武纪", 0.98),
                _anchor("m1", "concept:glass", "concept", "玻璃基板", 0.90),
                _anchor("m1", "concept:advanced", "concept", "先进封装", 0.90),
                _anchor("m1", "theme:power", "theme", "电源", 0.72),
            ]
        },
        config=AnchorRankingConfig(max_anchors_per_message=3),
    )

    assert [item.anchor_type for item in ranked["m1"]].count("stock") == 1
    assert {item.name for item in ranked["m1"]} == {"寒武纪", "玻璃基板", "先进封装"}


def test_rank_anchor_batch_uses_stock_and_topic_buckets():
    ranked = rank_anchor_batch(
        {
            "m1": [
                _anchor("m1", "stock:a", "stock", "股票A", 0.98),
                _anchor("m1", "stock:b", "stock", "股票B", 0.98),
                _anchor("m1", "stock:c", "stock", "股票C", 0.98),
                _anchor("m1", "stock:d", "stock", "股票D", 0.98),
                _anchor("m1", "concept:one", "concept", "玻璃基板", 0.90),
                _anchor("m1", "concept:two", "concept", "先进封装", 0.90),
                _anchor("m1", "concept:three", "concept", "半导体", 0.90),
                _anchor("m1", "theme:four", "theme", "算力", 0.84),
                _anchor("m1", "theme:five", "theme", "电源", 0.84),
            ]
        },
        config=AnchorRankingConfig(max_anchors_per_message=7),
    )

    items = ranked["m1"]
    assert len(items) == 7
    assert sum(item.anchor_type == "stock" for item in items) == 3
    assert sum(item.anchor_type != "stock" for item in items) == 4


def test_rank_anchor_batch_does_not_overfill_stock_bucket():
    ranked = rank_anchor_batch(
        {
            "m1": [
                _anchor("m1", "stock:a", "stock", "股票A", 0.98),
                _anchor("m1", "stock:b", "stock", "股票B", 0.98),
                _anchor("m1", "stock:c", "stock", "股票C", 0.98),
                _anchor("m1", "stock:d", "stock", "股票D", 0.98),
                _anchor("m1", "stock:e", "stock", "股票E", 0.98),
                _anchor("m1", "concept:one", "concept", "PCB", 0.90),
            ]
        },
        config=AnchorRankingConfig(max_anchors_per_message=7),
    )

    assert len(ranked["m1"]) == 4
    assert sum(item.anchor_type == "stock" for item in ranked["m1"]) == 3
    assert sum(item.anchor_type != "stock" for item in ranked["m1"]) == 1


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
        evidence=[{"text": name, "match_type": "exact"}],
        extractor_version="test",
        trade_date="20260604",
        created_at=now,
        updated_at=now,
    )
