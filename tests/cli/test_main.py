from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.models import RawMessage
from radar.core.market import (
    EnsureMarketAnchorsResult,
    RefreshMarketAnchorDerivativesResult,
    RefreshMarketAnchorsResult,
)
from radar.core.market import RefreshMarketThemeNormalizationResult
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.usecases import ClassifyRangeResult, IngestRangeResult, SmokeResult


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


def test_classify_messages_command_invokes_core_usecase(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_classify(
        config,
        *,
        source,
        start_time,
        end_time,
        chunk_hours,
        limit,
        force,
        use_llm,
        provider_name,
        provider_names,
        batch_size,
        max_concurrency,
        retry,
        low_confidence_threshold,
    ):
        calls.append(
            {
                "database": config.database_path,
                "source": source,
                "start_time": start_time,
                "end_time": end_time,
                "chunk_hours": chunk_hours,
                "limit": limit,
                "force": force,
                "use_llm": use_llm,
                "provider_name": provider_name,
                "provider_names": provider_names,
                "batch_size": batch_size,
                "max_concurrency": max_concurrency,
                "retry": retry,
                "low_confidence_threshold": low_confidence_threshold,
            }
        )
        return ClassifyRangeResult(
            run_id="run-456",
            source=source,
            start_time=start_time,
            end_time=end_time,
            chunk_count=2,
            empty_chunk_count=1,
            scanned_count=3,
            classified_count=3,
            inserted_count=3,
            llm_count=3,
            failed_llm_batches=0,
            distribution={"research": 2, "event": 1},
            status_distribution={"auto": 3},
        )

    monkeypatch.setattr("radar.cli.classify.classify_messages_range", fake_classify)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "classify",
            "messages",
            "--source",
            "group_message",
            "--start",
            "2026-06-04 10:00:00",
            "--end",
            "2026-06-04 12:00:00",
            "--chunk-hours",
            "1",
            "--limit",
            "200",
            "--batch-size",
            "8",
            "--max-concurrency",
            "4",
            "--provider-pool",
            "provider-a",
            "--provider-pool",
            "provider-b",
            "--retry",
            "needs_review",
            "--low-confidence-threshold",
            "0.7",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "chunks=2 empty=1 scanned=3 classified=3 inserted=3" in result.output
    assert "distribution: event=1 research=2" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "source": "个人群",
            "start_time": datetime.fromisoformat("2026-06-04T10:00:00"),
            "end_time": datetime.fromisoformat("2026-06-04T12:00:00"),
            "chunk_hours": 1,
            "limit": 200,
            "force": True,
            "use_llm": True,
            "provider_name": None,
            "provider_names": ["provider-a", "provider-b"],
            "batch_size": 8,
            "max_concurrency": 4,
            "retry": "needs_review",
            "low_confidence_threshold": 0.7,
        }
    ]


def test_anchor_update_command_invokes_market_anchor_update(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_ensure(config, *, trade_date, min_anchor_count, force):
        calls.append(
            {
                "database": config.database_path,
                "market_database": config.market_database_path,
                "trade_date": trade_date,
                "min_anchor_count": min_anchor_count,
                "force": force,
            }
        )
        return EnsureMarketAnchorsResult(
            trade_date=trade_date,
            requested_trade_date=trade_date,
            anchor_count=100,
            member_count=900,
            refreshed=True,
        )

    monkeypatch.setattr("radar.cli.anchor.ensure_market_anchors", fake_ensure)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "anchor",
            "update",
            "--trade-date",
            "20260604",
            "--min-anchors",
            "120",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "anchor/update: trade_date=20260604 requested=20260604 status=refreshed anchors=100 members=900" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "market_database": tmp_path / "data" / "market.sqlite3",
            "trade_date": "20260604",
            "min_anchor_count": 120,
            "force": True,
        }
    ]


def test_anchor_update_command_reports_skip_reason(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    monkeypatch.setattr(
        "radar.cli.anchor.ensure_market_anchors",
        lambda *args, **kwargs: EnsureMarketAnchorsResult(
            trade_date="20260604",
            requested_trade_date="20260604",
            anchor_count=100,
            member_count=900,
            skipped_reason="anchor 词库已存在",
        ),
    )

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "anchor",
            "update",
            "--trade-date",
            "20260604",
        ],
    )

    assert result.exit_code == 0
    assert "status=skipped" in result.output
    assert "reason=anchor 词库已存在" in result.output


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


def test_market_anchor_refresh_command_invokes_core(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_refresh(config, *, trade_date, use_cache):
        calls.append(
            {
                "market_database": config.market_database_path,
                "trade_date": trade_date,
                "use_cache": use_cache,
            }
        )
        return RefreshMarketAnchorsResult(
            trade_date=trade_date,
            anchor_count=3,
            member_count=5,
            source_counts={"dc_concept": 1, "dc_concept_cons": 2},
        )

    monkeypatch.setattr("radar.cli.market.refresh_market_anchors", fake_refresh)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "market",
            "anchors",
            "refresh",
            "--trade-date",
            "20260604",
            "--no-cache",
        ],
    )

    assert result.exit_code == 0
    assert "market/anchors: trade_date=20260604 anchors=3 members=5" in result.output
    assert "sources={'dc_concept': 1, 'dc_concept_cons': 2}" in result.output
    assert calls == [
        {
            "market_database": tmp_path / "data" / "market.sqlite3",
            "trade_date": "20260604",
            "use_cache": False,
        }
    ]


def test_market_anchor_ensure_command_invokes_core(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_ensure(config, *, trade_date, min_anchor_count, force, use_cache):
        calls.append(
            {
                "market_database": config.market_database_path,
                "trade_date": trade_date,
                "min_anchor_count": min_anchor_count,
                "force": force,
                "use_cache": use_cache,
            }
        )
        return EnsureMarketAnchorsResult(
            trade_date=trade_date,
            anchor_count=1099,
            member_count=6031,
            refreshed=False,
            skipped_reason="anchor 词库已存在",
        )

    monkeypatch.setattr("radar.cli.market.ensure_market_anchors", fake_ensure)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "market",
            "anchors",
            "ensure",
            "--trade-date",
            "20260604",
            "--min-anchors",
            "1000",
        ],
    )

    assert result.exit_code == 0
    assert "market/anchors: trade_date=20260604 status=skipped anchors=1099 members=6031" in result.output
    assert "reason=anchor 词库已存在" in result.output
    assert calls == [
        {
            "market_database": tmp_path / "data" / "market.sqlite3",
            "trade_date": "20260604",
            "min_anchor_count": 1000,
            "force": False,
            "use_cache": True,
        }
    ]


def test_market_anchor_rebuild_derived_command_invokes_core(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_rebuild(config):
        calls.append({"market_database": config.market_database_path})
        return RefreshMarketAnchorDerivativesResult(
            latest_trade_date="20260605",
            current_count=10,
            span_count=8,
        )

    monkeypatch.setattr("radar.cli.market.refresh_market_anchor_derivatives", fake_rebuild)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "market",
            "anchors",
            "rebuild-derived",
        ],
    )

    assert result.exit_code == 0
    assert "market/anchors/derived: latest_trade_date=20260605 current=10 spans=8" in result.output
    assert calls == [{"market_database": tmp_path / "data" / "market.sqlite3"}]


def test_market_themes_rebuild_command_invokes_core(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    def fake_rebuild(config, *, rebuild_anchor_derivatives=True):
        calls.append(
            {
                "market_database": config.market_database_path,
                "rebuild_anchor_derivatives": rebuild_anchor_derivatives,
            }
        )
        return RefreshMarketThemeNormalizationResult(
            latest_trade_date="20260605",
            theme_count=5,
            source_link_count=8,
            membership_count=12,
            current_stock_count=10,
            covered_stock_count=9,
            coverage_ratio=0.9,
            ambiguous_stock_count=1,
        )

    monkeypatch.setattr("radar.cli.market.refresh_market_theme_normalization", fake_rebuild)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "market",
            "themes",
            "rebuild",
            "--skip-anchor-derived",
        ],
    )

    assert result.exit_code == 0
    assert "market/themes: latest_trade_date=20260605 themes=5 links=8 memberships=12" in result.output
    assert "covered=9/10 coverage=90.0% ambiguous=1" in result.output
    assert calls == [
        {
            "market_database": tmp_path / "data" / "market.sqlite3",
            "rebuild_anchor_derivatives": False,
        }
    ]


def test_dashboard_command_starts_uvicorn(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path)
    calls: list[dict] = []

    class FakeProcess:
        def __init__(self, args, cwd, env, start_new_session):
            self.args = args
            self.cwd = cwd
            self.env = env
            self.start_new_session = start_new_session
            self.pid = 123
            self.poll_count = 0
            calls.append(
                {
                    "args": args,
                    "cwd": cwd,
                    "env_config_dir": env.get("RADAR_CONFIG_DIR"),
                    "env_api_base": env.get("VITE_RADAR_API_BASE"),
                    "start_new_session": start_new_session,
                }
            )

        def poll(self):
            self.poll_count += 1
            return 0 if self.poll_count > 1 and "uvicorn" in self.args else None

        def wait(self, timeout):
            return 0

    monkeypatch.setattr("radar.cli.dashboard.subprocess.Popen", FakeProcess)
    monkeypatch.setattr("radar.cli.dashboard.time.sleep", lambda _: None)

    monkeypatch.setattr("radar.cli.dashboard._stop_children", lambda children: None)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(config_dir),
            "dashboard",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--ui-port",
            "5174",
        ],
    )

    assert result.exit_code == 0
    assert "dashboard: http://127.0.0.1:5174" in result.output
    assert "api: http://127.0.0.1:9000" in result.output
    assert calls == [
        {
            "args": [
                sys.executable,
                "-m",
                "uvicorn",
                "radar.web.server.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
            ],
            "cwd": Path(__file__).resolve().parents[2],
            "env_config_dir": str(config_dir),
            "env_api_base": "http://127.0.0.1:9000",
            "start_new_session": True,
        },
        {
            "args": [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5174",
            ],
            "cwd": Path(__file__).resolve().parents[2] / "web" / "ui",
            "env_config_dir": str(config_dir),
            "env_api_base": "http://127.0.0.1:9000",
            "start_new_session": True,
        },
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
