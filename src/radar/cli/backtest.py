from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import cast

import click

from radar.cli.context import load_cli_config
from radar.core.models import MessageSource
from radar.core.usecases.recommendation_backtest import (
    DEFAULT_BENCHMARK_TS_CODE,
    DEFAULT_BACKTEST_WINDOWS,
    BacktestGroupBy,
    RecommendationBacktestRefreshResult,
    RecommendationBacktestSummaryResult,
    refresh_recommendation_backtests,
    summarize_recommendation_backtests,
)
from radar.core.usecases.recommendation_backtest.events import RECOMMENDATION_EVENT_EXTRACTOR_VERSION

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}


@click.group()
def backtest() -> None:
    """推荐消息胜率回测。"""


@backtest.command("refresh")
@click.option("--as-of", "as_of_text", default="today", show_default=True, help="截至日期，YYYY-MM-DD 或 today。")
@click.option("--window-days", type=click.IntRange(1, 365), default=30, show_default=True)
@click.option("--window", "windows", type=click.IntRange(1, 30), multiple=True, help="T+N 窗口，可重复。")
@click.option("--benchmark", "benchmark_ts_code", default=DEFAULT_BENCHMARK_TS_CODE, show_default=True)
@click.option("--extractor-version", default=RECOMMENDATION_EVENT_EXTRACTOR_VERSION, show_default=True)
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option("--min-classification-confidence", type=click.FloatRange(0, 1), default=0.7, show_default=True)
@click.option("--force", is_flag=True, help="重新计算已完成窗口。")
@click.pass_context
def refresh_command(
    ctx: click.Context,
    as_of_text: str,
    window_days: int,
    windows: tuple[int, ...],
    benchmark_ts_code: str,
    extractor_version: str,
    source_key: str,
    min_classification_confidence: float,
    force: bool,
) -> None:
    """扫描最近 N 天 recommendation+stock 事件，补齐成熟 T+N。"""

    result = refresh_recommendation_backtests(
        load_cli_config(ctx),
        as_of=_parse_date(as_of_text),
        window_days=window_days,
        windows=list(windows) or list(DEFAULT_BACKTEST_WINDOWS),
        source=_SOURCE_MAP[source_key],
        min_classification_confidence=min_classification_confidence,
        extractor_version=extractor_version,
        benchmark_ts_code=benchmark_ts_code,
        force=force,
    )
    _echo_refresh(result)


@backtest.command("summary")
@click.option("--as-of", "as_of_text", default="today", show_default=True, help="截至日期，YYYY-MM-DD 或 today。")
@click.option("--window-days", type=click.IntRange(1, 365), default=30, show_default=True)
@click.option("--window", "windows", type=click.IntRange(1, 30), multiple=True, help="T+N 窗口，可重复。")
@click.option(
    "--group-by",
    type=click.Choice(["source", "source_stock", "stock", "analyst", "analyst_stock", "sector", "analyst_sector"]),
    default="source",
    show_default=True,
)
@click.option("--min-count", type=click.IntRange(1, 1000), default=1, show_default=True)
@click.option("--top", type=click.IntRange(1, 200), default=20, show_default=True)
@click.pass_context
def summary_command(
    ctx: click.Context,
    as_of_text: str,
    window_days: int,
    windows: tuple[int, ...],
    group_by: str,
    min_count: int,
    top: int,
) -> None:
    """查看来源候选 / 来源+股票 / 股票维度的回测画像。"""

    as_of = _parse_date(as_of_text)
    start_time = datetime.combine(as_of - timedelta(days=window_days - 1), time.min)
    end_time = datetime.combine(as_of + timedelta(days=1), time.min)
    result = summarize_recommendation_backtests(
        load_cli_config(ctx),
        start_time=start_time,
        end_time=end_time,
        group_by=cast(BacktestGroupBy, group_by),
        windows=list(windows) or list(DEFAULT_BACKTEST_WINDOWS),
        min_count=min_count,
        limit=top,
    )
    _echo_summary(result)


def _echo_refresh(result: RecommendationBacktestRefreshResult) -> None:
    click.echo(
        f"backtest/refresh: events={result.event_count} new_events={result.inserted_event_count} "
        f"refreshed={result.refreshed_count} skipped={result.skipped_complete_count} "
        f"pending={result.pending_count} missing_price={result.missing_price_count} "
        f"failed={result.failed_count} windows={','.join(str(item) for item in result.windows)} "
        f"run_id={result.run_id}"
    )


def _echo_summary(result: RecommendationBacktestSummaryResult) -> None:
    click.echo(
        f"backtest/summary: rows={result.row_count} group_by={result.group_by} "
        f"windows={','.join(str(item) for item in result.windows)}"
    )
    for index, row in enumerate(result.rows, start=1):
        label = row.source_candidate or row.analyst_display_name or row.sector_name or "-"
        if row.sector_name and row.analyst_display_name:
            label = f"{label} {row.sector_name}"
        if row.ts_code:
            label = f"{label} {row.stock_name or ''}({row.ts_code})".strip()
        metrics = " ".join(_format_metric(row.metrics, window) for window in result.windows)
        click.echo(f"{index}. {label} events={row.event_count} {metrics}")


def _format_metric(metrics: dict[str, float | int], window: int) -> str:
    sample_count = int(metrics.get(f"sample_count_t{window}") or 0)
    win_rate = metrics.get(f"win_rate_t{window}")
    avg_return = metrics.get(f"avg_return_t{window}")
    avg_excess = metrics.get(f"avg_excess_t{window}")
    win_text = f"{float(win_rate) * 100:.1f}%" if win_rate is not None else "--"
    ret_text = f"{float(avg_return) * 100:.2f}%" if avg_return is not None else "--"
    excess_text = f"{float(avg_excess) * 100:.2f}%" if avg_excess is not None else "--"
    return f"T+{window}:n={sample_count},win={win_text},ret={ret_text},excess={excess_text}"


def _parse_date(value: str) -> date:
    if value == "today":
        return date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    return date.fromisoformat(value)
