from __future__ import annotations

from typing import cast

import click

from radar.cli.context import load_cli_config, parse_datetime
from radar.core.models import ClassificationRetryMode, MessageSource
from radar.core.usecases import ClassifyRangeResult, classify_messages_range

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}


@click.group()
def classify() -> None:
    """整理派生数据。"""


@classify.command("messages")
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.option("--force", is_flag=True, help="重新分类已存在结果的消息。")
@click.option("--chunk-hours", type=click.IntRange(1, 24), default=1, show_default=True)
@click.option("--limit", type=click.IntRange(1, 5000), default=500, show_default=True)
@click.option("--batch-size", type=click.IntRange(1, 64), default=16, show_default=True)
@click.option("--max-concurrency", type=click.IntRange(1, 32), default=None)
@click.option("--provider", "provider_name", help="指定单个 LLM provider。")
@click.option("--provider-pool", "provider_pool", multiple=True, help="可重复传入多个 provider。")
@click.option(
    "--retry",
    type=click.Choice(["needs_review", "unknown", "low_confidence"]),
    default=None,
    help="重跑已有分类中的目标子集。",
)
@click.option("--low-confidence-threshold", type=click.FloatRange(0, 1), default=0.65, show_default=True)
@click.option("--no-llm", is_flag=True, help="不调用 LLM，写入待复核 unknown。")
@click.pass_context
def classify_messages_command(
    ctx: click.Context,
    source_key: str,
    start_text: str,
    end_text: str,
    force: bool,
    chunk_hours: int,
    limit: int,
    batch_size: int,
    max_concurrency: int | None,
    provider_name: str | None,
    provider_pool: tuple[str, ...],
    retry: str | None,
    low_confidence_threshold: float,
    no_llm: bool,
) -> None:
    """按时间窗口分类消息并写入 SQLite。"""

    if provider_name and provider_pool:
        raise click.ClickException("--provider 和 --provider-pool 只能二选一")
    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    if end_time <= start_time:
        raise click.ClickException("--end 必须晚于 --start")

    result = classify_messages_range(
        load_cli_config(ctx),
        source=_SOURCE_MAP[source_key],
        start_time=start_time,
        end_time=end_time,
        chunk_hours=chunk_hours,
        limit=limit,
        force=force,
        use_llm=not no_llm,
        provider_name=provider_name,
        provider_names=list(provider_pool) or None,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        retry=cast(ClassificationRetryMode | None, retry),
        low_confidence_threshold=low_confidence_threshold,
    )
    _echo_classify_result(result)


def _echo_classify_result(result: ClassifyRangeResult) -> None:
    click.echo(
        f"classify/messages: chunks={result.chunk_count} empty={result.empty_chunk_count} "
        f"scanned={result.scanned_count} classified={result.classified_count} "
        f"inserted={result.inserted_count} llm={result.llm_count} "
        f"failed_batches={result.failed_llm_batches} run_id={result.run_id}"
    )
    if result.distribution:
        summary = " ".join(f"{key}={value}" for key, value in sorted(result.distribution.items()))
        click.echo(f"distribution: {summary}")
