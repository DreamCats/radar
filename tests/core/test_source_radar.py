from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases.source import SourceStructure, extract_source_structures, scan_source_signals
from radar.core.usecases.source.storage import upsert_source_structures


def test_source_extract_uses_provider_pool_and_persists_structures(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T09:00:00", "PCB 是成熟赛道"),
        _message("m2", "2026-06-02T09:14:00", "正在半导体化的PCB"),
        _message("m3", "2026-06-02T09:30:00", "AI电源成为新方向"),
    ]
    _seed_messages(config, messages)
    calls: list[str | None] = []

    def fake_extractor(_config, batch: list[RawMessage], provider_name: str | None):
        calls.append(provider_name)
        return [
            _structure(
                message,
                anchor="PCB" if "PCB" in message.raw_content else "AI",
                modifier="半导体化" if "PCB" in message.raw_content else "电源",
                novel="半导体化的PCB" if "PCB" in message.raw_content else "AI电源",
                provider=provider_name,
            )
            for message in batch
            if message.message_id != "m1"
        ]

    result = extract_source_structures(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-03T00:00:00"),
        batch_size=1,
        max_concurrency=10,
        provider_names=["p1", "p2", "p3", "p4"],
        llm_batch_extractor=fake_extractor,
    )

    assert result.max_concurrency == 3
    assert set(calls) == {"p1", "p2", "p3"}
    assert result.inserted_count == 2
    with connect(config.database_path) as conn:
        assert conn.execute("SELECT COUNT(*) AS c FROM source_structures").fetchone()["c"] == 2


def test_source_extract_records_failed_provider_metrics(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T09:00:00", "AI电源成为新方向"),
        _message("m2", "2026-06-01T09:10:00", "PCB 国产替代出现新变化"),
        _message("m3", "2026-06-01T09:20:00", "机器人零部件有突破"),
    ]
    _seed_messages(config, messages)

    def fake_extractor(_config, batch: list[RawMessage], provider_name: str | None):
        if provider_name == "p2":
            raise RuntimeError("provider timeout")
        return [
            _structure(
                batch[0],
                anchor="AI",
                modifier="电源",
                novel="AI电源",
                provider=provider_name,
            )
        ]

    result = extract_source_structures(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-02T00:00:00"),
        batch_size=1,
        max_concurrency=3,
        provider_names=["p1", "p2", "p3"],
        llm_batch_extractor=fake_extractor,
    )

    assert result.failed_llm_batches == 1
    assert result.failed_llm_batch_details[0].provider == "p2"
    assert result.failed_llm_batch_details[0].error_type == "RuntimeError"
    assert "provider timeout" in str(result.failed_llm_batch_details[0].error_message)
    assert {item.provider for item in result.provider_stats} == {"p1", "p2", "p3"}
    with connect(config.database_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM runs WHERE kind = 'source_extract' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    metadata = json.loads(str(row["metadata_json"]))
    assert metadata["failed_llm_batch_details"][0]["provider"] == "p2"
    assert metadata["provider_stats"][0]["failed_count"] == 1


def test_source_scan_detects_seed_spreading_and_mapping(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("old", "2026-05-20T09:00:00", "PCB 是成熟赛道"),
        _message("seed", "2026-06-01T09:14:00", "正在半导体化的PCB"),
        _message("later1", "2026-06-01T10:00:00", "半导体化的PCB 开始扩散", group_name="群A", sender="a"),
        _message("later2", "2026-06-01T11:00:00", "半导体化的PCB 有预期差", group_name="群B", sender="b"),
        _message("stock", "2026-06-01T12:00:00", "半导体化的PCB 推荐本川智能", group_name="群C", sender="c"),
    ]
    _seed_messages(config, messages)
    with connect(config.database_path) as conn:
        init_db(conn)
        upsert_source_structures(
            conn,
            [_structure(messages[1], anchor="PCB", modifier="半导体化", novel="半导体化的PCB")],
        )
        _insert_event(conn, messages[4], stock_name="本川智能", ts_code="300964.SZ")

    early = scan_source_signals(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-02T00:00:00"),
        as_of_time=datetime.fromisoformat("2026-06-01T09:30:00"),
        lookback_days=30,
        limit=5,
        save_snapshot=False,
    )
    late = scan_source_signals(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-02T00:00:00"),
        as_of_time=datetime.fromisoformat("2026-06-01T12:30:00"),
        lookback_days=30,
        limit=5,
        save_snapshot=False,
    )

    assert early.candidates[0].status == "source_seed"
    assert early.candidates[0].prior_anchor_mentions == 1
    assert early.candidates[0].prior_exact_mentions == 0
    assert late.candidates[0].status == "mapped"
    assert late.candidates[0].followup_senders == 3
    assert late.candidates[0].mapped_stocks == ["本川智能"]


def test_source_scan_prefers_spreading_and_filters_weak_seed(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("old-gpu", "2026-05-20T09:00:00", "GPU 是成熟算力锚点"),
        _message("old-pcb", "2026-05-20T09:10:00", "PCB 是成熟产业链"),
        _message("old-cny", "2026-05-20T09:20:00", "人民币 是宏观锚点"),
        _message("spread", "2026-06-01T09:00:00", "GPU与CPU深度协同 是 AI 服务器新变化", group_name="群A", sender="a"),
        _message("spread2", "2026-06-01T10:00:00", "GPU与CPU深度协同 开始被讨论", group_name="群B", sender="b"),
        _message("spread3", "2026-06-01T11:00:00", "继续关注 GPU与CPU深度协同", group_name="群C", sender="c"),
        _message("seed", "2026-06-01T09:30:00", "台积电玻璃基板技术线路 关注 PCB 产业链", group_name="群A", sender="d"),
        _message("weak", "2026-06-01T09:40:00", "深度低估的人民币 是大叙事", group_name="群A", sender="e"),
    ]
    _seed_messages(config, messages)
    with connect(config.database_path) as conn:
        init_db(conn)
        upsert_source_structures(
            conn,
            [
                _structure(messages[3], anchor="GPU", modifier="CPU深度协同", novel="GPU与CPU深度协同"),
                _structure(messages[6], anchor="PCB", modifier="台积电玻璃基板", novel="台积电玻璃基板技术线路"),
                _structure(messages[7], anchor="人民币", modifier="深度低估", novel="深度低估的人民币"),
            ],
        )

    result = scan_source_signals(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-02T00:00:00"),
        as_of_time=datetime.fromisoformat("2026-06-01T12:00:00"),
        lookback_days=30,
        limit=10,
        save_snapshot=False,
    )

    assert result.candidates[0].status == "spreading_watch"
    assert result.candidates[0].novel_span == "GPU与CPU深度协同"
    assert "深度低估的人民币" not in {item.novel_span for item in result.candidates}


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _seed_messages(config: RadarConfig, messages: list[RawMessage]) -> None:
    with connect(config.database_path) as conn:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message) for message in messages])


def _message(
    message_id: str,
    message_time: str,
    content: str,
    *,
    group_name: str = "测试群",
    sender: str | None = None,
) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=sender or f"sender-{message_id}",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat(message_time),
        fetch_window="20260601090000-20260601120000",
    )


def _classification(message: RawMessage) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-01T12:30:00")
    return MessageClassification(
        message_id=message.message_id,
        category="research",
        confidence=0.9,
        reason="源头雷达测试",
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _structure(
    message: RawMessage,
    *,
    anchor: str,
    modifier: str,
    novel: str,
    provider: str | None = None,
) -> SourceStructure:
    now = datetime.fromisoformat("2026-06-01T12:31:00")
    return SourceStructure(
        structure_id=f"{message.message_id}-{anchor}-{modifier}",
        message_id=message.message_id,
        source=message.source,
        sender=message.sender,
        group_name=message.group_name,
        message_time=message.message_time,
        is_candidate=True,
        anchor_span=anchor,
        modifier_span=modifier,
        novel_span=novel,
        relation_type="A化B" if modifier.endswith("化") else "modifier-anchor",
        relation_evidence=novel,
        ask_question=f"{novel} 是真的产业变化吗？",
        confidence=0.9,
        llm_provider=provider,
        prompt_version="test",
        extractor_version="source-structure-v1",
        created_at=now,
        updated_at=now,
    )


def _insert_event(conn, message: RawMessage, *, stock_name: str, ts_code: str) -> None:
    now = datetime.fromisoformat("2026-06-01T12:31:00")
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
            "event-stock",
            message.message_id,
            message.source,
            message.sender,
            message.group_name,
            "recommendation",
            0.9,
            ts_code,
            stock_name,
            "bullish",
            message.message_time.isoformat(),
            message.message_time.strftime("%Y%m%d"),
            "test-event",
            0.9,
            None,
            message.sender,
            None,
            None,
            "concept",
            "半导体化的PCB",
            0.9,
            now.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
