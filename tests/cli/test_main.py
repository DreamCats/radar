from __future__ import annotations

from datetime import datetime

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases import IngestRangeResult


def test_query_reads_messages_from_config_database(tmp_path):
    config_dir = _config_dir(tmp_path)
    conn = connect(tmp_path / "radar.sqlite3")
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "query",
            "--source",
            "group_message",
            "--keyword",
            "固态",
        ],
    )

    assert result.exit_code == 0
    assert "个人群" in result.output
    assert "固态电池" in result.output


def test_ingest_wechat_invokes_core_usecase(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_ingest(config, *, source_key, start_time, end_time, force, chunk_hours, concurrency):
        calls.append(
            {
                "database": config.database_path,
                "source_key": source_key,
                "start_time": start_time,
                "end_time": end_time,
                "force": force,
                "chunk_hours": chunk_hours,
                "concurrency": concurrency,
            }
        )
        return IngestRangeResult(
            source_key=source_key,
            source="个人群",
            start_time=start_time,
            end_time=end_time,
            chunk_count=24,
            skipped_count=0,
            raw_count=3,
            filtered_count=1,
            stored_count=2,
        )

    monkeypatch.setattr("radar.cli.ingest.ingest_wechat_range", fake_ingest)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "ingest",
            "wechat",
            "--source",
            "group_message",
            "--start",
            "2026-06-03",
            "--end",
            "2026-06-04",
            "--force",
            "--chunk-hours",
            "2",
            "--concurrency",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert "chunks=24 skipped=0 raw=3 filtered=1 stored=2" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "source_key": "group_message",
            "start_time": datetime.fromisoformat("2026-06-03T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-04T00:00:00"),
            "force": True,
            "chunk_hours": 2,
            "concurrency": 3,
        }
    ]


def _config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        f"""
storage:
  database: {tmp_path / "radar.sqlite3"}
filters:
  group_blacklist_patterns:
    - 小学
""".strip()
    )
    (config_dir / "secrets.yaml").write_text(
        """
wechat:
  endpoints:
    wechat_main:
      base_url: https://example.invalid/wechat
""".strip()
    )
    return config_dir


def _message() -> RawMessage:
    return RawMessage(
        message_id="m1",
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat("2026-06-03T09:30:00"),
        raw_content="固态电池测试消息",
        group_name="东财策略",
        fetch_time=datetime.fromisoformat("2026-06-03T09:31:00"),
        fetch_window="20260603090000-20260603100000",
    )
