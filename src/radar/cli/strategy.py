from __future__ import annotations

from datetime import datetime

import click

from radar.cli.context import load_cli_config
from radar.core.storage import connect, init_db
from radar.core.usecases.stock_evidence_chain import build_stock_evidence_chain, index_stock_mentions


@click.group()
def strategy() -> None:
    """策略离线命令。"""


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
@click.option("--force-llm", is_flag=True, help="忽略证据签名缓存，强制重新调用 LLM。")
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
    force_llm: bool,
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
        force_llm=force_llm,
    )
    click.echo(
        "strategy/evidence-chain/run: "
        f"as_of={result.as_of.isoformat()} indexed_messages={result.indexed_messages} "
        f"mentions={result.mention_count} candidates={result.candidate_count} "
        f"judged={result.judged_count} reused={result.reused_count} failed={result.failed_count}"
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


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T", 1))
