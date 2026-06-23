from __future__ import annotations

from datetime import date, datetime, time, timedelta

import click

from radar.cli.context import load_cli_config
from radar.core.models import MessageSource
from radar.core.usecases.analyst_mentions import (
    DEFAULT_ANALYST_MENTION_WINDOWS,
    DEFAULT_BENCHMARK_TS_CODE,
    DEFAULT_COOLDOWN_TRADE_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_CLASSIFICATION_CONFIDENCE,
    DEFAULT_REMOTE_PRICE_FETCH,
    AnalystMentionEvidenceResult,
    AnalystMentionRefreshResult,
    AnalystMentionSummaryResult,
    list_analyst_stock_mention_evidence,
    refresh_analyst_stock_mentions,
    summarize_analyst_stock_mentions,
)

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}


@click.group()
def backtest() -> None:
    """分析师股票提及胜率回测。"""


@backtest.command("refresh")
@click.option(
    "--as-of",
    "as_of_text",
    default="today",
    show_default=True,
    help="截至日期，YYYY-MM-DD 或 today。",
)
@click.option(
    "--lookback-days",
    type=click.IntRange(1, 120),
    default=DEFAULT_LOOKBACK_DAYS,
    show_default=True,
)
@click.option(
    "--window",
    "windows",
    type=click.IntRange(1, 30),
    multiple=True,
    help="T+N 窗口，可重复。",
)
@click.option(
    "--benchmark",
    "benchmark_ts_code",
    default=DEFAULT_BENCHMARK_TS_CODE,
    show_default=True,
)
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option(
    "--cooldown-trade-days",
    type=click.IntRange(0, 30),
    default=DEFAULT_COOLDOWN_TRADE_DAYS,
    show_default=True,
)
@click.option(
    "--min-classification-confidence",
    type=click.FloatRange(0, 1),
    default=DEFAULT_MIN_CLASSIFICATION_CONFIDENCE,
    show_default=True,
)
@click.option(
    "--remote-prices/--no-remote-prices",
    default=DEFAULT_REMOTE_PRICE_FETCH,
    show_default=True,
    help="是否用 Tushare 按需补齐缺失行情。",
)
@click.pass_context
def refresh_command(
    ctx: click.Context,
    as_of_text: str,
    lookback_days: int,
    windows: tuple[int, ...],
    benchmark_ts_code: str,
    source_key: str,
    cooldown_trade_days: int,
    min_classification_confidence: float,
    remote_prices: bool,
) -> None:
    """刷新分析师股票提及后的 T+N 表现。"""

    result = refresh_analyst_stock_mentions(
        load_cli_config(ctx),
        as_of=_parse_date(as_of_text),
        lookback_days=lookback_days,
        windows=list(windows) or list(DEFAULT_ANALYST_MENTION_WINDOWS),
        source=_SOURCE_MAP[source_key],
        cooldown_trade_days=cooldown_trade_days,
        min_classification_confidence=min_classification_confidence,
        remote_price_fetch=remote_prices,
        benchmark_ts_code=benchmark_ts_code,
    )
    _echo_refresh(result)


@backtest.command("summary")
@click.option(
    "--as-of",
    "as_of_text",
    default="today",
    show_default=True,
    help="截至日期，YYYY-MM-DD 或 today。",
)
@click.option(
    "--lookback-days",
    type=click.IntRange(1, 120),
    default=DEFAULT_LOOKBACK_DAYS,
    show_default=True,
)
@click.option(
    "--window",
    "windows",
    type=click.IntRange(1, 30),
    multiple=True,
    help="T+N 窗口，可重复。",
)
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option("--min-count", type=click.IntRange(1, 1000), default=3, show_default=True)
@click.option("--top", type=click.IntRange(1, 200), default=20, show_default=True)
@click.option("--include-broad-list", is_flag=True, help="把单条消息命中很多股票的样本也纳入汇总。")
@click.pass_context
def summary_command(
    ctx: click.Context,
    as_of_text: str,
    lookback_days: int,
    windows: tuple[int, ...],
    source_key: str,
    min_count: int,
    top: int,
    include_broad_list: bool,
) -> None:
    """查看分析师近期股票提及后的表现榜。"""

    as_of = _parse_date(as_of_text)
    end_time = datetime.combine(as_of + timedelta(days=1), time.min)
    start_time = end_time - timedelta(days=lookback_days)
    result = summarize_analyst_stock_mentions(
        load_cli_config(ctx),
        start_time=start_time,
        end_time=end_time,
        windows=list(windows) or list(DEFAULT_ANALYST_MENTION_WINDOWS),
        source=_SOURCE_MAP[source_key],
        min_count=min_count,
        limit=top,
        include_broad_list=include_broad_list,
    )
    _echo_summary(result)


@backtest.command("evidence")
@click.option(
    "--as-of",
    "as_of_text",
    default="today",
    show_default=True,
    help="截至日期，YYYY-MM-DD 或 today。",
)
@click.option(
    "--lookback-days",
    type=click.IntRange(1, 120),
    default=DEFAULT_LOOKBACK_DAYS,
    show_default=True,
)
@click.option("--window", type=click.IntRange(1, 30), default=5, show_default=True)
@click.option("--analyst", help="分析师显示名片段或 analyst_id。")
@click.option("--ts-code", help="股票 ts_code，例如 600900.SH。")
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option("--top", type=click.IntRange(1, 200), default=20, show_default=True)
@click.option("--exclude-broad-list", is_flag=True, help="按汇总口径排除 broad_list 样本。")
@click.pass_context
def evidence_command(
    ctx: click.Context,
    as_of_text: str,
    lookback_days: int,
    window: int,
    analyst: str | None,
    ts_code: str | None,
    source_key: str,
    top: int,
    exclude_broad_list: bool,
) -> None:
    """查看分析师股票提及的原文片段和 T+N 表现。"""

    as_of = _parse_date(as_of_text)
    end_time = datetime.combine(as_of + timedelta(days=1), time.min)
    start_time = end_time - timedelta(days=lookback_days)
    result = list_analyst_stock_mention_evidence(
        load_cli_config(ctx),
        start_time=start_time,
        end_time=end_time,
        window=window,
        analyst=analyst,
        ts_code=ts_code,
        source=_SOURCE_MAP[source_key],
        limit=top,
        include_broad_list=not exclude_broad_list,
    )
    _echo_evidence(result)


def _echo_refresh(result: AnalystMentionRefreshResult) -> None:
    click.echo(
        f"backtest/refresh: scanned={result.scanned_message_count} "
        f"stock_hit_messages={result.stock_hit_message_count} "
        f"raw_mentions={result.raw_mention_count} "
        f"broker_filtered={result.source_broker_filtered_count} "
        f"broad_list={result.broad_list_mention_count} "
        f"effective={result.effective_mention_count} repeated={result.repeated_mention_count} "
        f"prewarm_days={result.prewarm_trade_day_count} "
        f"prewarm_rows={result.prewarm_daily_row_count} "
        f"refreshed={result.refreshed_count} pending={result.pending_count} "
        f"missing_price={result.missing_price_count} failed={result.failed_count} "
        f"windows={','.join(str(item) for item in result.windows)} run_id={result.run_id}"
    )


def _echo_summary(result: AnalystMentionSummaryResult) -> None:
    click.echo(
        f"backtest/summary: rows={result.row_count} "
        f"windows={','.join(str(item) for item in result.windows)}"
    )
    for index, row in enumerate(result.rows, start=1):
        metrics = " ".join(_format_metric(row.metrics, window) for window in result.windows)
        click.echo(f"{index}. {row.analyst_display_name} events={row.event_count} {metrics}")


def _echo_evidence(result: AnalystMentionEvidenceResult) -> None:
    click.echo(f"backtest/evidence: rows={result.row_count} window={result.window_days}")
    for index, row in enumerate(result.rows, start=1):
        ret_text = _pct(row.return_rate)
        excess_text = _pct(row.excess_return_rate)
        status = row.status or "-"
        flags = ",".join(row.quality_flags) if row.quality_flags else "-"
        click.echo(
            f"{index}. {row.analyst_display_name} {row.stock_name}({row.ts_code}) "
            f"{row.message_time.isoformat()} status={status} "
            f"ret={ret_text} excess={excess_text} stocks={row.stock_count_in_message} "
            f"flags={flags} msg={row.message_id}"
        )
        click.echo(f"   {row.evidence_snippet}")


def _format_metric(metrics: dict[str, float | int], window: int) -> str:
    sample_count = int(metrics.get(f"sample_count_t{window}") or 0)
    positive_rate = metrics.get(f"positive_rate_t{window}")
    avg_return = metrics.get(f"avg_return_t{window}")
    avg_excess = metrics.get(f"avg_excess_t{window}")
    positive_text = f"{float(positive_rate) * 100:.1f}%" if positive_rate is not None else "--"
    ret_text = f"{float(avg_return) * 100:.2f}%" if avg_return is not None else "--"
    excess_text = f"{float(avg_excess) * 100:.2f}%" if avg_excess is not None else "--"
    return f"T+{window}:n={sample_count},pos={positive_text},ret={ret_text},excess={excess_text}"


def _parse_date(value: str) -> date:
    if value == "today":
        return date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    return date.fromisoformat(value)


def _pct(value: float | None) -> str:
    return f"{value * 100:.2f}%" if value is not None else "--"
