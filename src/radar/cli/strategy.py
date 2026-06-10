from __future__ import annotations

from datetime import datetime

import click

from radar.cli.context import load_cli_config
from radar.core.store import connect, init_db
from radar.core.usecases.stock_evidence_chain import build_stock_evidence_chain, index_stock_mentions
from radar.core.usecases.strategy.snapshots import (
    DEFAULT_SNAPSHOT_BENCHMARK,
    DEFAULT_SNAPSHOT_WINDOWS,
    backfill_strategy_snapshot_returns,
    save_strategy_snapshot,
)


@click.group()
def strategy() -> None:
    """发酵确认策略快照和验证。"""


@strategy.group("evidence-chain")
def evidence_chain() -> None:
    """个股证据链生命周期。"""


@evidence_chain.command("index")
@click.option("--start", "start_time", required=True, help="索引起点，例如 2026-05-01T15:00:00。")
@click.option("--end", "end_time", required=True, help="索引终点，例如 2026-06-09T15:00:00。")
@click.pass_context
def evidence_chain_index_command(ctx: click.Context, start_time: str, end_time: str) -> None:
    """增量建立消息-股票命中索引。"""

    result = index_stock_mentions(
        load_cli_config(ctx),
        start=_parse_time(start_time),
        end=_parse_time(end_time),
    )
    click.echo(
        "strategy/evidence-chain/index: "
        f"messages={result.scanned_messages} mentions={result.mention_count} changed={result.changed_count}"
    )


@evidence_chain.command("run")
@click.option("--as-of", "as_of_time", default=None, help="判断时间；默认用最新消息时间。")
@click.option("--window-start", default=None, help="新增窗口起点；默认 as-of 前一日 15:00。")
@click.option("--evidence-days", type=click.IntRange(7, 90), default=40, show_default=True)
@click.option("--limit", type=click.IntRange(1, 500), default=120, show_default=True)
@click.option("--llm/--no-llm", "run_llm", default=False, show_default=True)
@click.option("--llm-workers", type=click.IntRange(1, 64), default=16, show_default=True)
@click.option("--llm-provider", "llm_providers", multiple=True, help="LLM provider，可重复；不传走默认 provider。")
@click.option("--llm-model", default=None)
@click.pass_context
def evidence_chain_run_command(
    ctx: click.Context,
    as_of_time: str | None,
    window_start: str | None,
    evidence_days: int,
    limit: int,
    run_llm: bool,
    llm_workers: int,
    llm_providers: tuple[str, ...],
    llm_model: str | None,
) -> None:
    """生成候选池；可选并发调用 LLM 判断阶段。"""

    result = build_stock_evidence_chain(
        load_cli_config(ctx),
        as_of=_parse_time(as_of_time) if as_of_time else None,
        window_start=_parse_time(window_start) if window_start else None,
        evidence_days=evidence_days,
        limit=limit,
        run_llm=run_llm,
        llm_workers=llm_workers,
        llm_providers=list(llm_providers) or None,
        llm_model=llm_model,
    )
    click.echo(
        "strategy/evidence-chain/run: "
        f"as_of={result.as_of.isoformat()} indexed_messages={result.indexed_messages} "
        f"mentions={result.mention_count} candidates={result.candidate_count} "
        f"judged={result.judged_count} failed={result.failed_count}"
    )


@strategy.command("cleanup-deprecated")
@click.option("--confirm", is_flag=True, help="确认删除废弃策略表。")
@click.pass_context
def cleanup_deprecated_command(ctx: click.Context, confirm: bool) -> None:
    """删除已废弃的旧叙事生命周期表。"""

    tables = [
        "normalized_anchors",
        "narratives",
        "narrative_snapshots",
        "narrative_stocks",
        "narrative_stock_snapshots",
    ]
    if not confirm:
        click.echo("将删除废弃表：" + ", ".join(tables))
        click.echo("确认执行请追加 --confirm。")
        return
    config = load_cli_config(ctx)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    click.echo("strategy/cleanup-deprecated: dropped=" + ",".join(tables))


@strategy.command("snapshot")
@click.option("--days", type=click.IntRange(7, 180), default=30, show_default=True)
@click.option("--recent-days", type=click.IntRange(1, 30), default=7, show_default=True)
@click.option("--limit", type=click.IntRange(1, 50), default=12, show_default=True)
@click.pass_context
def snapshot_command(ctx: click.Context, days: int, recent_days: int, limit: int) -> None:
    """保存一次当前发酵确认策略输出。"""

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


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T", 1))
