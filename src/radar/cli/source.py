from __future__ import annotations

import click

from radar.cli.context import load_cli_config, parse_datetime
from radar.core.usecases.source import extract_source_structures, scan_source_signals


@click.group()
def source() -> None:
    """源头概念雷达。"""


@source.command("extract")
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.option("--limit", type=click.IntRange(1, 10000), default=500, show_default=True)
@click.option("--force", is_flag=True, help="重新抽取已处理消息。")
@click.option("--batch-size", type=click.IntRange(1, 30), default=24, show_default=True)
@click.option("--max-concurrency", type=click.IntRange(1, 32), default=10, show_default=True)
@click.option("--provider", "provider_name", help="指定单个 LLM provider。")
@click.option("--provider-pool", "provider_pool", multiple=True, help="可重复传入多个 provider；默认使用全部已配置 provider。")
@click.pass_context
def extract_command(
    ctx: click.Context,
    start_text: str,
    end_text: str,
    limit: int,
    force: bool,
    batch_size: int,
    max_concurrency: int,
    provider_name: str | None,
    provider_pool: tuple[str, ...],
) -> None:
    """抽取“锚点 + 修饰 + 新组合”结构。"""

    if provider_name and provider_pool:
        raise click.ClickException("--provider 和 --provider-pool 只能二选一")
    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    result = extract_source_structures(
        load_cli_config(ctx),
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        force=force,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        provider_name=provider_name,
        provider_names=list(provider_pool) or None,
    )
    click.echo(
        f"source/extract: scanned={result.scanned_count} extracted={result.extracted_count} "
        f"inserted={result.inserted_count} llm={result.llm_count} failed_batches={result.failed_llm_batches} "
        f"max_concurrency={result.max_concurrency} providers={','.join(str(item) for item in result.provider_pool)} "
        f"run_id={result.run_id}"
    )


@source.command("scan")
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.option("--as-of", "as_of_text", default=None, help="证据截止时间；默认等于 --end。")
@click.option("--lookback-days", type=click.IntRange(7, 180), default=60, show_default=True)
@click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
@click.option("--no-save", is_flag=True, help="只计算不写 source_signal_snapshots。")
@click.pass_context
def scan_command(
    ctx: click.Context,
    start_text: str,
    end_text: str,
    as_of_text: str | None,
    lookback_days: int,
    limit: int,
    no_save: bool,
) -> None:
    """按 as_of 扫描源头种子、扩散验证和个股映射。"""

    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    as_of_time = parse_datetime(as_of_text) if as_of_text else None
    result = scan_source_signals(
        load_cli_config(ctx),
        start_time=start_time,
        end_time=end_time,
        as_of_time=as_of_time,
        lookback_days=lookback_days,
        limit=limit,
        save_snapshot=not no_save,
    )
    click.echo(
        f"source/scan: candidates={result.candidate_count} shown={len(result.candidates)} "
        f"scanned={result.scanned_count} as_of={result.as_of_time.isoformat()}"
    )
    for index, item in enumerate(result.candidates, start=1):
        stocks = "、".join(item.mapped_stocks[:4]) or "-"
        click.echo(
            f"{index}. {item.novel_span} status={item.status} score={item.score} "
            f"novelty={item.novelty_strength} early={item.earliness_score} "
            f"asof={item.asof_mentions}次/{item.asof_groups}群 followup={item.followup_senders}人/{item.followup_groups}群 stocks={stocks}"
        )
        click.echo(
            f"   结构: {item.anchor_span}+{item.modifier_span} relation={item.relation_type} "
            f"首现={item.first_seen_time.strftime('%Y-%m-%d %H:%M:%S')} {item.first_sender}"
        )
        if item.ask_question:
            click.echo(f"   问题: {item.ask_question}")
