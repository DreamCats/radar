from __future__ import annotations

import click

from radar.cli.context import load_cli_config
from radar.core.usecases.strategy.snapshots import (
    DEFAULT_SNAPSHOT_BENCHMARK,
    DEFAULT_SNAPSHOT_WINDOWS,
    backfill_strategy_snapshot_returns,
    save_strategy_snapshot,
)


@click.group()
def strategy() -> None:
    """机会信号策略快照和验证。"""


@strategy.command("snapshot")
@click.option("--days", type=click.IntRange(7, 180), default=30, show_default=True)
@click.option("--recent-days", type=click.IntRange(1, 30), default=7, show_default=True)
@click.option("--limit", type=click.IntRange(1, 50), default=12, show_default=True)
@click.pass_context
def snapshot_command(ctx: click.Context, days: int, recent_days: int, limit: int) -> None:
    """保存一次当前机会信号策略输出。"""

    result = save_strategy_snapshot(load_cli_config(ctx), days=days, recent_days=recent_days, limit=limit)
    click.echo(
        f"strategy/snapshot: snapshot_id={result.snapshot_id} stocks={result.stock_count} "
        f"opportunities={result.opportunity_count} generated_at={result.generated_at.isoformat()}"
    )


@strategy.command("backfill")
@click.option("--window", "windows", type=click.IntRange(1, 30), multiple=True, help="T+N 窗口，可重复。")
@click.option("--benchmark", "benchmark_ts_code", default=DEFAULT_SNAPSHOT_BENCHMARK, show_default=True)
@click.option("--snapshot-id", default=None, help="只回填某个快照；默认回填全部快照。")
@click.pass_context
def backfill_command(
    ctx: click.Context,
    windows: tuple[int, ...],
    benchmark_ts_code: str,
    snapshot_id: str | None,
) -> None:
    """用本地 K 线回填快照股票的 T+N 表现。"""

    result = backfill_strategy_snapshot_returns(
        load_cli_config(ctx),
        windows=list(windows) or list(DEFAULT_SNAPSHOT_WINDOWS),
        benchmark_ts_code=benchmark_ts_code,
        snapshot_id=snapshot_id,
    )
    click.echo(
        f"strategy/backfill: snapshots={result.snapshot_count} stocks={result.stock_count} "
        f"refreshed={result.refreshed_count} pending={result.pending_count} "
        f"missing_price={result.missing_price_count} failed={result.failed_count} "
        f"windows={','.join(str(item) for item in result.windows)}"
    )
