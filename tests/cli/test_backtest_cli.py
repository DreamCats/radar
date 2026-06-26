from __future__ import annotations

from datetime import date, datetime

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.usecases.analyst_mentions import (
    AnalystMentionEvidenceItem,
    AnalystMentionEvidenceResult,
    AnalystMentionRefreshResult,
    AnalystMentionSummaryResult,
    AnalystMentionSummaryRow,
)


def test_backtest_refresh_command_invokes_analyst_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_refresh(
        config,
        *,
        as_of,
        lookback_days,
        windows,
        source,
        cooldown_trade_days,
        remote_price_fetch,
        benchmark_ts_code,
    ):
        calls.append(
            {
                "database": config.database_path,
                "as_of": as_of,
                "lookback_days": lookback_days,
                "windows": windows,
                "source": source,
                "cooldown_trade_days": cooldown_trade_days,
                "remote_price_fetch": remote_price_fetch,
                "benchmark_ts_code": benchmark_ts_code,
            }
        )
        return AnalystMentionRefreshResult(
            run_id="run-analyst",
            as_of=as_of,
            start_time=datetime.fromisoformat("2026-04-30T00:00:00"),
            end_time=datetime.fromisoformat("2026-06-09T00:00:00"),
            windows=windows,
            benchmark_ts_code=benchmark_ts_code,
            scanned_message_count=8,
            stock_hit_message_count=4,
            raw_mention_count=5,
            source_broker_filtered_count=1,
            broad_list_mention_count=2,
            effective_mention_count=3,
            repeated_mention_count=2,
            prewarm_trade_day_count=2,
            prewarm_daily_row_count=9000,
            refreshed_count=6,
            pending_count=1,
        )

    monkeypatch.setattr("radar.cli.backtest.refresh_analyst_stock_mentions", fake_refresh)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "backtest",
            "refresh",
            "--as-of",
            "2026-06-08",
            "--lookback-days",
            "40",
            "--window",
            "1",
            "--window",
            "5",
            "--source",
            "group_message",
            "--benchmark",
            "000300.SH",
            "--cooldown-trade-days",
            "5",
            "--remote-prices",
        ],
    )

    assert result.exit_code == 0
    assert "backtest/refresh: scanned=8 stock_hit_messages=4 raw_mentions=5" in result.output
    assert "broker_filtered=1 broad_list=2 effective=3 repeated=2" in result.output
    assert "prewarm_days=2 prewarm_rows=9000" in result.output
    assert "refreshed=6 pending=1" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "as_of": date(2026, 6, 8),
            "lookback_days": 40,
            "windows": [1, 5],
            "source": "个人群",
            "cooldown_trade_days": 5,
            "remote_price_fetch": True,
            "benchmark_ts_code": "000300.SH",
        }
    ]


def test_backtest_summary_command_invokes_analyst_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_summary(
        config,
        *,
        start_time,
        end_time,
        windows,
        source,
        min_count,
        limit,
        include_broad_list,
    ):
        calls.append(
            {
                "database": config.database_path,
                "start_time": start_time,
                "end_time": end_time,
                "windows": windows,
                "source": source,
                "min_count": min_count,
                "limit": limit,
                "include_broad_list": include_broad_list,
            }
        )
        return AnalystMentionSummaryResult(
            start_time=start_time,
            end_time=end_time,
            windows=windows,
            row_count=1,
            rows=[
                AnalystMentionSummaryRow(
                    analyst_id="an_1",
                    analyst_display_name="张三",
                    event_count=4,
                    latest_event_time=datetime.fromisoformat("2026-06-08T10:00:00"),
                    metrics={
                        "sample_count_t5": 4,
                        "positive_rate_t5": 0.75,
                        "avg_return_t5": 0.12,
                        "avg_excess_t5": 0.04,
                    },
                )
            ],
        )

    monkeypatch.setattr("radar.cli.backtest.summarize_analyst_stock_mentions", fake_summary)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "backtest",
            "summary",
            "--as-of",
            "2026-06-08",
            "--lookback-days",
            "40",
            "--window",
            "5",
            "--source",
            "group_message",
            "--min-count",
            "2",
            "--top",
            "10",
            "--include-broad-list",
        ],
    )

    assert result.exit_code == 0
    assert "backtest/summary: rows=1 windows=5" in result.output
    assert "张三 events=4 T+5:n=4,pos=75.0%,ret=12.00%,excess=4.00%" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "start_time": datetime.fromisoformat("2026-04-30T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-09T00:00:00"),
            "windows": [5],
            "source": "个人群",
            "min_count": 2,
            "limit": 10,
            "include_broad_list": True,
        }
    ]


def test_backtest_evidence_command_invokes_analyst_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_evidence(
        config,
        *,
        start_time,
        end_time,
        window,
        analyst,
        ts_code,
        source,
        limit,
        include_broad_list,
    ):
        calls.append(
            {
                "database": config.database_path,
                "start_time": start_time,
                "end_time": end_time,
                "window": window,
                "analyst": analyst,
                "ts_code": ts_code,
                "source": source,
                "limit": limit,
                "include_broad_list": include_broad_list,
            }
        )
        return AnalystMentionEvidenceResult(
            start_time=start_time,
            end_time=end_time,
            window_days=window,
            row_count=1,
            rows=[
                AnalystMentionEvidenceItem(
                    mention_id="mention-1",
                    message_id="m1",
                    analyst_id="an_1",
                    analyst_display_name="张三",
                    ts_code="600900.SH",
                    stock_name="长江电力",
                    message_time=datetime.fromisoformat("2026-06-08T10:00:00"),
                    evidence_snippet="继续关注长江电力的水电逻辑",
                    stock_count_in_message=8,
                    quality_flags=("broad_list",),
                    window_days=5,
                    status="succeeded",
                    target_trade_date="20260615",
                    return_rate=0.12,
                    excess_return_rate=0.04,
                )
            ],
        )

    monkeypatch.setattr("radar.cli.backtest.list_analyst_stock_mention_evidence", fake_evidence)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "backtest",
            "evidence",
            "--as-of",
            "2026-06-08",
            "--lookback-days",
            "40",
            "--window",
            "5",
            "--analyst",
            "张三",
            "--ts-code",
            "600900.SH",
            "--source",
            "group_message",
            "--top",
            "5",
            "--exclude-broad-list",
        ],
    )

    assert result.exit_code == 0
    assert "backtest/evidence: rows=1 window=5" in result.output
    assert "张三 长江电力(600900.SH)" in result.output
    assert "stocks=8 flags=broad_list" in result.output
    assert "继续关注长江电力的水电逻辑" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "start_time": datetime.fromisoformat("2026-04-30T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-09T00:00:00"),
            "window": 5,
            "analyst": "张三",
            "ts_code": "600900.SH",
            "source": "个人群",
            "limit": 5,
            "include_broad_list": False,
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
