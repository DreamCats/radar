from __future__ import annotations

from datetime import date, datetime

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.usecases.recommendation_backtest import (
    RecommendationBacktestRefreshResult,
    RecommendationBacktestSummaryResult,
    RecommendationBacktestSummaryRow,
)


def test_backtest_refresh_command_invokes_core_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_refresh(
        config,
        *,
        as_of,
        window_days,
        windows,
        source,
        min_classification_confidence,
        extractor_version,
        benchmark_ts_code,
        force,
    ):
        calls.append(
            {
                "database": config.database_path,
                "as_of": as_of,
                "window_days": window_days,
                "windows": windows,
                "source": source,
                "min_classification_confidence": min_classification_confidence,
                "extractor_version": extractor_version,
                "benchmark_ts_code": benchmark_ts_code,
                "force": force,
            }
        )
        start_time = datetime.fromisoformat("2026-05-01T00:00:00")
        end_time = datetime.fromisoformat("2026-05-06T00:00:00")
        return RecommendationBacktestRefreshResult(
            run_id="run-bt",
            as_of=as_of,
            start_time=start_time,
            end_time=end_time,
            windows=windows,
            benchmark_ts_code=benchmark_ts_code,
            event_count=3,
            inserted_event_count=2,
            refreshed_count=5,
            skipped_complete_count=1,
            pending_count=4,
            missing_price_count=0,
            failed_count=0,
        )

    monkeypatch.setattr("radar.cli.backtest.refresh_recommendation_backtests", fake_refresh)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "backtest",
            "refresh",
            "--as-of",
            "2026-06-05",
            "--window-days",
            "30",
            "--window",
            "1",
            "--window",
            "5",
            "--source",
            "group_message",
            "--extractor-version",
            "test-anchor",
            "--benchmark",
            "000300.SH",
            "--min-classification-confidence",
            "0.75",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "backtest/refresh: events=3 new_events=2 refreshed=5 skipped=1 pending=4" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "as_of": date(2026, 6, 5),
            "window_days": 30,
            "windows": [1, 5],
            "source": "个人群",
            "min_classification_confidence": 0.75,
            "extractor_version": "test-anchor",
            "benchmark_ts_code": "000300.SH",
            "force": True,
        }
    ]


def test_backtest_summary_command_invokes_core_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_summary(config, *, start_time, end_time, group_by, windows, min_count, limit):
        calls.append(
            {
                "database": config.database_path,
                "start_time": start_time,
                "end_time": end_time,
                "group_by": group_by,
                "windows": windows,
                "min_count": min_count,
                "limit": limit,
            }
        )
        return RecommendationBacktestSummaryResult(
            start_time=start_time,
            end_time=end_time,
            group_by=group_by,
            windows=windows,
            row_count=1,
            rows=[
                RecommendationBacktestSummaryRow(
                    key="an_1|industry|白酒",
                    analyst_id="an_1",
                    analyst_display_name="张三-分析师",
                    sector_anchor_type="industry",
                    sector_name="白酒",
                    event_count=3,
                    metrics={"sample_count_t5": 3, "win_rate_t5": 0.6667, "avg_return_t5": 0.12},
                )
            ],
        )

    monkeypatch.setattr("radar.cli.backtest.summarize_recommendation_backtests", fake_summary)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "backtest",
            "summary",
            "--as-of",
            "2026-06-05",
            "--window-days",
            "10",
            "--window",
            "5",
            "--group-by",
            "analyst_sector",
            "--min-count",
            "2",
            "--top",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert "backtest/summary: rows=1 group_by=analyst_sector windows=5" in result.output
    assert "张三-分析师 白酒 events=3 T+5:n=3,win=66.7%,ret=12.00%" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "start_time": datetime.fromisoformat("2026-05-27T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-06T00:00:00"),
            "group_by": "analyst_sector",
            "windows": [5],
            "min_count": 2,
            "limit": 5,
        }
    ]


def _config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        f"""
storage:
  data_dir: {tmp_path}
  database: {tmp_path / "radar.sqlite3"}
""",
        encoding="utf-8",
    )
    return config_dir
