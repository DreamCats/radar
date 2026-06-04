from __future__ import annotations

import importlib
from collections import Counter
from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.runs import get_run
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases import classify_batch_with_llm, classify_messages, classify_messages_range


def test_classify_messages_uses_llm_and_skips_existing(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "推荐关注玻璃基板，弹性较大"),
            _message("m2", "2026-06-04T09:00:00", "今晚 20:30 电话会，欢迎报名参会"),
        ],
    )

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        provider_name: str | None,
    ) -> list[MessageClassification]:
        assert provider_name == "test-provider"
        return [
            _classification(batch[0], "recommendation", 0.91, "LLM 判断为推荐"),
            _classification(batch[1], "event", 0.92, "LLM 判断为会议"),
        ]

    first = classify_messages(
        config,
        limit=10,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )
    second = classify_messages(
        config,
        limit=10,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert first.scanned_count == 2
    assert first.inserted_count == 2
    assert first.llm_count == 2
    assert first.rule_count == 0
    assert first.distribution == {"recommendation": 1, "event": 1}
    assert first.status_distribution == {"auto": 2}
    assert second.scanned_count == 0
    assert second.inserted_count == 0

    run = get_run(config.database_path, first.run_id)
    assert run is not None
    assert run.kind == "message_classify"
    assert run.status == "succeeded"


def test_classify_messages_writes_llm_result(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [_message("m1", "2026-06-04T10:00:00", "这个标题没有明显关键词 | 行业专题")],
    )

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        provider_name: str | None,
    ) -> list[MessageClassification]:
        assert provider_name == "test-provider"
        return [_classification(batch[0], "industry", 0.91, "LLM 判断为产业事件")]

    result = classify_messages(
        config,
        limit=10,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.llm_count == 1
    assert result.rule_count == 0
    assert result.distribution == {"industry": 1}

    conn = connect(config.database_path)
    try:
        row = conn.execute("SELECT * FROM message_classifications WHERE message_id = 'm1'").fetchone()
    finally:
        conn.close()

    assert row["category"] == "industry"
    assert row["classifier_type"] == "llm"
    assert row["llm_provider"] == "test-provider"


def test_classify_messages_falls_back_to_unknown_when_llm_batch_fails(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "推荐关注玻璃基板，弹性较大"),
            _message("m2", "2026-06-04T09:00:00", "今晚 20:30 电话会，欢迎报名参会"),
        ],
    )

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        if batch[0].message_id == "m1":
            raise RuntimeError("llm failed")
        return [_classification(batch[0], "industry", 0.88, "LLM 覆盖")]

    result = classify_messages(
        config,
        limit=10,
        batch_size=1,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.failed_llm_batches == 1
    assert result.llm_count == 1
    assert result.rule_count == 0
    assert result.distribution == {"unknown": 1, "industry": 1}
    assert result.status_distribution == {"needs_review": 1, "auto": 1}


def test_classify_messages_uses_provider_pool(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "消息一"),
            _message("m2", "2026-06-04T09:00:00", "消息二"),
            _message("m3", "2026-06-04T08:00:00", "消息三"),
        ],
    )
    seen_providers: list[str | None] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_providers.append(provider_name)
        return [_classification(batch[0], "chat", 0.90, f"来自 {provider_name}")]

    result = classify_messages(
        config,
        limit=10,
        batch_size=1,
        provider_names=["provider-a", "provider-b"],
        max_concurrency=2,
        llm_batch_classifier=fake_llm,
    )

    assert result.llm_count == 3
    assert Counter(seen_providers) == Counter({"provider-a": 2, "provider-b": 1})


def test_classify_messages_range_drains_window_and_skips_existing(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:10:00", "消息一"),
            _message("m2", "2026-06-04T10:20:00", "消息二"),
            _message("m3", "2026-06-04T10:30:00", "消息三"),
        ],
    )
    seen_ids: list[str] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_ids.extend(message.message_id for message in batch)
        return [_classification(message, "research", 0.90, "LLM 分类") for message in batch]

    first = classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        limit=2,
        batch_size=2,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )
    second = classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        limit=2,
        batch_size=2,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert first.chunk_count == 1
    assert first.scanned_count == 3
    assert first.inserted_count == 3
    assert first.llm_count == 3
    assert first.distribution == {"research": 3}
    assert second.scanned_count == 0
    assert second.inserted_count == 0
    assert Counter(seen_ids) == Counter({"m1": 1, "m2": 1, "m3": 1})

    run = get_run(config.database_path, first.run_id)
    assert run is not None
    assert run.kind == "message_classify_range"
    assert run.status == "succeeded"


def test_classify_messages_range_uses_half_open_chunks(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:30:00", "十点半"),
            _message("m2", "2026-06-04T11:00:00", "整点边界"),
            _message("m3", "2026-06-04T11:30:00", "十一点半"),
        ],
    )
    seen_ids: list[str] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_ids.extend(message.message_id for message in batch)
        return [_classification(message, "event", 0.90, "LLM 分类") for message in batch]

    result = classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T12:00:00"),
        chunk_hours=1,
        limit=10,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.chunk_count == 2
    assert result.scanned_count == 3
    assert Counter(seen_ids) == Counter({"m1": 1, "m2": 1, "m3": 1})


def test_classify_messages_range_force_updates_without_duplicate_rows(tmp_path):
    config = _config(tmp_path)
    _seed_messages(config, [_message("m1", "2026-06-04T10:10:00", "消息一")])
    categories = ["research", "event"]

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        return [_classification(batch[0], categories.pop(0), 0.90, "LLM 分类")]

    classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )
    result = classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        force=True,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    conn = connect(config.database_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count, MAX(category) AS category FROM message_classifications"
        ).fetchone()
    finally:
        conn.close()

    assert result.scanned_count == 1
    assert result.inserted_count == 0
    assert row["count"] == 1
    assert row["category"] == "event"


def test_classify_messages_range_retries_needs_review_only(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:10:00", "需要重试"),
        _message("m2", "2026-06-04T10:20:00", "已自动分类"),
    ]
    _seed_messages(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "unknown", 0.0, "批次失败", status="needs_review"),
            _classification(messages[1], "research", 0.90, "已分类", status="auto"),
        ],
    )
    seen_ids: list[str] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_ids.extend(message.message_id for message in batch)
        return [_classification(message, "event", 0.90, "重试成功") for message in batch]

    result = classify_messages_range(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        retry="needs_review",
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.scanned_count == 1
    assert result.inserted_count == 0
    assert seen_ids == ["m1"]

    conn = connect(config.database_path)
    try:
        rows = conn.execute(
            "SELECT message_id, category FROM message_classifications ORDER BY message_id"
        ).fetchall()
    finally:
        conn.close()
    assert [(row["message_id"], row["category"]) for row in rows] == [("m1", "event"), ("m2", "research")]


def test_classify_messages_retries_unknown_but_keeps_confirmed(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:10:00", "未知分类"),
        _message("m2", "2026-06-04T10:20:00", "人工确认未知"),
    ]
    _seed_messages(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "unknown", 0.20, "待重试", status="needs_review"),
            _classification(messages[1], "unknown", 0.20, "人工确认", status="confirmed"),
        ],
    )
    seen_ids: list[str] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_ids.extend(message.message_id for message in batch)
        return [_classification(message, "research", 0.90, "重试成功") for message in batch]

    result = classify_messages(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        retry="unknown",
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.scanned_count == 1
    assert seen_ids == ["m1"]


def test_classify_messages_retries_low_confidence(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:10:00", "低置信"),
        _message("m2", "2026-06-04T10:20:00", "高置信"),
    ]
    _seed_messages(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "industry", 0.40, "低置信", status="needs_review"),
            _classification(messages[1], "industry", 0.90, "高置信", status="auto"),
        ],
    )
    seen_ids: list[str] = []

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        seen_ids.extend(message.message_id for message in batch)
        return [_classification(message, "research", 0.90, "重试成功") for message in batch]

    result = classify_messages(
        config,
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        retry="low_confidence",
        low_confidence_threshold=0.65,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.scanned_count == 1
    assert seen_ids == ["m1"]


def test_classify_messages_writes_finished_batch_before_next_batch(tmp_path):
    config = _config(tmp_path)
    _seed_messages(
        config,
        [
            _message("m1", "2026-06-04T10:00:00", "消息一"),
            _message("m2", "2026-06-04T09:00:00", "消息二"),
        ],
    )

    def fake_llm(
        _config: RadarConfig,
        batch: list[RawMessage],
        _provider_name: str | None,
    ) -> list[MessageClassification]:
        if batch[0].message_id == "m2":
            conn = connect(config.database_path)
            try:
                row = conn.execute(
                    "SELECT category FROM message_classifications WHERE message_id = 'm1'"
                ).fetchone()
            finally:
                conn.close()
            assert row["category"] == "research"
        return [_classification(batch[0], "research", 0.90, "LLM 分类")]

    result = classify_messages(
        config,
        limit=10,
        batch_size=1,
        max_concurrency=1,
        provider_name="test-provider",
        llm_batch_classifier=fake_llm,
    )

    assert result.llm_count == 2
    assert result.inserted_count == 2


def test_classify_batch_with_llm_disables_thinking(monkeypatch, tmp_path):
    config = _config(tmp_path)
    seen_kwargs = {}
    classify_module = importlib.import_module("radar.core.usecases.classification.messages")

    def fake_resolve_provider(_config, *, provider_name=None, task=None):
        assert provider_name == "test-provider"
        assert task == "classify"
        return "test-provider", None

    def fake_chat_json_list(_config, _messages, **kwargs):
        seen_kwargs.update(kwargs)
        return [{"index": 1, "category": "research", "confidence": 0.9, "reason": "LLM 分类"}]

    monkeypatch.setattr(classify_module, "resolve_provider", fake_resolve_provider)
    monkeypatch.setattr(classify_module, "chat_json_list", fake_chat_json_list)

    results = classify_batch_with_llm(
        config,
        [_message("m1", "2026-06-04T10:00:00", "研究观点")],
        "test-provider",
    )

    assert seen_kwargs["provider_name"] == "test-provider"
    assert seen_kwargs["disable_thinking"] is True
    assert results[0].category == "research"


def test_classify_batch_remaps_tool_ad_to_research(monkeypatch, tmp_path):
    config = _config(tmp_path)
    classify_module = importlib.import_module("radar.core.usecases.classification.messages")

    def fake_resolve_provider(_config, *, provider_name=None, task=None):
        return "test-provider", None

    def fake_chat_json_list(_config, _messages, **_kwargs):
        return [{"index": 1, "category": "tool_ad", "confidence": 0.9, "reason": "金融信息入口"}]

    monkeypatch.setattr(classify_module, "resolve_provider", fake_resolve_provider)
    monkeypatch.setattr(classify_module, "chat_json_list", fake_chat_json_list)

    results = classify_batch_with_llm(
        config,
        [_message("m1", "2026-06-04T10:00:00", "智能投研系统榜单")],
        "test-provider",
    )

    assert results[0].category == "research"
    assert results[0].status == "auto"


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})


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
