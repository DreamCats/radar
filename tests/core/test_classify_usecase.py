from __future__ import annotations

import importlib
from collections import Counter
from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.runs import get_run
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases import classify_batch_with_llm, classify_messages


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
    classify_module = importlib.import_module("radar.core.usecases.classify_messages")

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


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})


def _seed_messages(config: RadarConfig, messages: list[RawMessage]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
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
) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status="auto",
        classifier_type="llm",
        llm_provider="test-provider",
        prompt_version="test",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )
