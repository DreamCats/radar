from __future__ import annotations

from datetime import datetime

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases import IngestRangeResult, SmokeResult


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
            run_id="run-123",
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
    assert "chunks=24 skipped=0 raw=3 filtered=1 stored=2 run_id=run-123" in result.output
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


def test_llm_smoke_command_invokes_usecase(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_test_llm(config, *, provider_name, task, model):
        calls.append(
            {
                "database": config.database_path,
                "provider_name": provider_name,
                "task": task,
                "model": model,
            }
        )
        return SmokeResult("llm", "openai/gpt-test", "request ok", sample="ok")

    monkeypatch.setattr("radar.cli.test.test_llm", fake_test_llm)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "test",
            "llm",
            "--provider",
            "main",
            "--task",
            "classify",
            "--model",
            "gpt-test",
        ],
    )

    assert result.exit_code == 0
    assert "llm | openai/gpt-test | request ok | sample=ok" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "provider_name": "main",
            "task": "classify",
            "model": "gpt-test",
        }
    ]


def test_market_smoke_command_invokes_usecase(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_test_market(config, *, date_text, use_cache):
        calls.append(
            {
                "market_database": config.market_database_path,
                "date_text": date_text,
                "use_cache": use_cache,
            }
        )
        return SmokeResult(
            "market",
            "tushare/trade_cal/20260603",
            "request ok",
            sample="cal_date=20260603",
            row_count=1,
        )

    monkeypatch.setattr("radar.cli.test.test_market", fake_test_market)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "test",
            "market",
            "--date",
            "20260603",
            "--no-cache",
        ],
    )

    assert result.exit_code == 0
    assert "market | tushare/trade_cal/20260603 | request ok | rows=1" in result.output
    assert "sample=cal_date=20260603" in result.output
    assert calls == [
        {
            "market_database": tmp_path / "data" / "market.sqlite3",
            "date_text": "20260603",
            "use_cache": False,
        }
    ]


def _config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        f"""
storage:
  data_dir: {tmp_path / "data"}
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
