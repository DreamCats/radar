from __future__ import annotations

import click

from radar.cli.context import load_cli_config, parse_datetime
from radar.core.usecases import IngestRangeResult, ingest_wechat_range


@click.group()
def ingest() -> None:
    """写入数据。"""


@ingest.command("wechat")
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="微信数据源。",
)
@click.option(
    "--start",
    "start_text",
    required=True,
    help="开始时间，如 2026-06-03 或 2026-06-03 09:00:00。",
)
@click.option(
    "--end",
    "end_text",
    required=True,
    help="结束时间，如 2026-06-04 或 2026-06-03 18:00:00。",
)
@click.option("--force", is_flag=True, help="即使时间窗已写入，也重新拉取。")
@click.option(
    "--chunk-hours",
    type=click.IntRange(1, 24),
    default=1,
    show_default=True,
    help="按多少小时切片拉取。",
)
@click.option(
    "--concurrency",
    type=click.IntRange(1, 16),
    default=4,
    show_default=True,
    help="每个数据源的并发拉取窗口数。",
)
@click.pass_context
def ingest_wechat(
    ctx: click.Context,
    source_key: str,
    start_text: str,
    end_text: str,
    force: bool,
    chunk_hours: int,
    concurrency: int,
) -> None:
    """从微信 API 拉取一个时间窗并写入 SQLite。"""

    config = load_cli_config(ctx)
    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    if end_time <= start_time:
        raise click.ClickException("--end 必须晚于 --start")

    source_keys = list(config.wechat.sources) if source_key == "all" else [source_key]
    for key in source_keys:
        result = ingest_wechat_range(
            config,
            source_key=key,
            start_time=start_time,
            end_time=end_time,
            force=force,
            chunk_hours=chunk_hours,
            concurrency=concurrency,
        )
        _echo_ingest_result(result)


def _echo_ingest_result(result: IngestRangeResult) -> None:
    click.echo(
        f"{result.source_key}/{result.source}: "
        f"chunks={result.chunk_count} skipped={result.skipped_count} "
        f"raw={result.raw_count} filtered={result.filtered_count} stored={result.stored_count}"
    )
