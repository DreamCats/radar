from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig, RadarSecrets, WechatEndpointSecret, WechatSecrets
from radar.core.models import MessageSource, RawMessage
from radar.core.runs import get_run
from radar.core.store import connect, init_db, record_fetch_window
from radar.core.usecases import ingest_wechat_range, ingest_wechat_window


def test_ingest_wechat_window_writes_and_skips_existing(tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-04T09:00:00")
    end_time = datetime.fromisoformat("2026-06-04T10:00:00")
    calls = 0

    def fetcher(
        base_url: str,
        source: MessageSource,
        start: datetime,
        end: datetime,
        timeout: float,
    ) -> list[RawMessage]:
        nonlocal calls
        calls += 1
        assert base_url == "https://example.invalid/wechat"
        return [
            _message("m1", "东财策略"),
            _message("m2", "汇师小学二年级（1）班"),
        ]

    first = ingest_wechat_window(
        config,
        source_key="group_message",
        start_time=start_time,
        end_time=end_time,
        fetcher=fetcher,
    )
    second = ingest_wechat_window(
        config,
        source_key="group_message",
        start_time=start_time,
        end_time=end_time,
        fetcher=fetcher,
    )

    assert calls == 1
    assert first.raw_count == 2
    assert first.filtered_count == 1
    assert first.stored_count == 1
    assert first.run_id is not None
    assert second.skipped_existing is True
    assert second.run_id is not None

    conn = connect(config.database_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fetch_windows").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    finally:
        conn.close()

    first_run = get_run(config.database_path, first.run_id)
    second_run = get_run(config.database_path, second.run_id)
    assert first_run is not None
    assert first_run.status == "succeeded"
    assert first_run.raw_count == 2
    assert first_run.filtered_count == 1
    assert second_run is not None
    assert second_run.status == "skipped"


def test_ingest_wechat_range_fetches_chunks_and_skips_existing(tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-04T09:00:00")
    end_time = datetime.fromisoformat("2026-06-04T12:00:00")
    calls: list[tuple[datetime, datetime]] = []

    def fetcher(
        base_url: str,
        source: MessageSource,
        start: datetime,
        end: datetime,
        timeout: float,
    ) -> list[RawMessage]:
        calls.append((start, end))
        messages = [_message(f"m{start.hour}", "东财策略")]
        if start.hour == 9:
            messages.append(_message("m-blacklisted", "汇师小学二年级（1）班"))
        return messages

    first = ingest_wechat_range(
        config,
        source_key="group_message",
        start_time=start_time,
        end_time=end_time,
        chunk_hours=1,
        concurrency=2,
        fetcher=fetcher,
    )
    second = ingest_wechat_range(
        config,
        source_key="group_message",
        start_time=start_time,
        end_time=end_time,
        chunk_hours=1,
        concurrency=2,
        fetcher=fetcher,
    )

    assert first.chunk_count == 3
    assert first.skipped_count == 0
    assert first.raw_count == 4
    assert first.filtered_count == 1
    assert first.stored_count == 3
    assert first.run_id is not None
    assert second.skipped_count == 3
    assert second.run_id is not None
    assert len(calls) == 3

    conn = connect(config.database_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM fetch_windows").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    finally:
        conn.close()

    second_run = get_run(config.database_path, second.run_id)
    assert second_run is not None
    assert second_run.status == "skipped"
    assert second_run.metadata["skipped_count"] == 3


def test_ingest_wechat_range_skips_chunks_covered_by_larger_window(tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-04T09:00:00")
    end_time = datetime.fromisoformat("2026-06-04T12:00:00")
    conn = connect(config.database_path)
    try:
        init_db(conn)
        record_fetch_window(
            conn,
            source="个人群",
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            fetched_at="2026-06-04T12:01:00",
            raw_count=3,
            stored_count=3,
            filtered_count=0,
        )
    finally:
        conn.close()

    def fetcher(
        base_url: str,
        source: MessageSource,
        start: datetime,
        end: datetime,
        timeout: float,
    ) -> list[RawMessage]:
        raise AssertionError("covered chunks should not be fetched")

    result = ingest_wechat_range(
        config,
        source_key="group_message",
        start_time=start_time,
        end_time=end_time,
        chunk_hours=1,
        concurrency=2,
        fetcher=fetcher,
    )

    assert result.chunk_count == 3
    assert result.skipped_count == 3
    assert result.raw_count == 0
    assert result.stored_count == 0
    assert result.run_id is not None

    run = get_run(config.database_path, result.run_id)
    assert run is not None
    assert run.status == "skipped"


def test_ingest_wechat_range_records_failed_run(tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-04T09:00:00")
    end_time = datetime.fromisoformat("2026-06-04T10:00:00")

    def fetcher(
        base_url: str,
        source: MessageSource,
        start: datetime,
        end: datetime,
        timeout: float,
    ) -> list[RawMessage]:
        raise RuntimeError("微信 API 超时")

    try:
        ingest_wechat_range(
            config,
            source_key="group_message",
            start_time=start_time,
            end_time=end_time,
            fetcher=fetcher,
        )
    except RuntimeError:
        pass

    conn = connect(config.database_path)
    try:
        row = conn.execute("SELECT run_id FROM runs WHERE status = 'failed'").fetchone()
    finally:
        conn.close()

    assert row is not None
    run = get_run(config.database_path, row["run_id"])
    assert run is not None
    assert run.error_message == "微信 API 超时"


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"},
        filters={"group_blacklist_patterns": ["小学"]},
        secrets=RadarSecrets(
            wechat=WechatSecrets(
                endpoints={"wechat_main": WechatEndpointSecret(base_url="https://example.invalid/wechat")}
            )
        ),
    )


def _message(message_id: str, group_name: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat("2026-06-04T09:30:00"),
        raw_content="测试消息",
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T09:31:00"),
        fetch_window="20260604090000-20260604100000",
    )
