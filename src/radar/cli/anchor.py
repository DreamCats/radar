from __future__ import annotations

from typing import cast

import click

from radar.cli.context import load_cli_config, parse_datetime
from radar.core.market_anchors import ensure_market_anchors
from radar.core.models import MessageCategory, MessageSource
from radar.core.usecases import AnchorRangeResult, anchor_messages_range
from radar.core.usecases.anchoring import DEFAULT_ANCHOR_CATEGORIES

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}
_CATEGORY_CHOICES = ["research", "recommendation", "event", "industry", "tool_ad", "chat", "unknown"]


@click.group()
def anchor() -> None:
    """抽取消息市场 anchor。"""


@anchor.command("messages")
@click.option("--trade-date", required=True, help="anchor 词库交易日，格式 YYYYMMDD。")
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option(
    "--category",
    "categories",
    type=click.Choice(_CATEGORY_CHOICES),
    multiple=True,
    help=f"分类，可重复；不传默认 {','.join(DEFAULT_ANCHOR_CATEGORIES)}。",
)
@click.option("--min-classification-confidence", type=click.FloatRange(0, 1), default=None)
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.option("--force", is_flag=True, help="重新抽取已处理消息。")
@click.option("--chunk-hours", type=click.IntRange(1, 24), default=1, show_default=True)
@click.option("--limit", type=click.IntRange(1, 5000), default=500, show_default=True)
@click.option("--max-anchors", type=click.IntRange(1, 50), default=7, show_default=True)
@click.pass_context
def anchor_messages_command(
    ctx: click.Context,
    trade_date: str,
    source_key: str,
    categories: tuple[str, ...],
    min_classification_confidence: float | None,
    start_text: str,
    end_text: str,
    force: bool,
    chunk_hours: int,
    limit: int,
    max_anchors: int,
) -> None:
    """按时间窗口抽取消息 anchor 并写入 SQLite。"""

    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    if end_time <= start_time:
        raise click.ClickException("--end 必须晚于 --start")

    config = load_cli_config(ctx)
    anchors = ensure_market_anchors(config, trade_date=trade_date, min_anchor_count=100)
    if anchors.trade_date != trade_date:
        click.echo(f"market/anchors: {anchors.skipped_reason or f'使用 {anchors.trade_date} 的 anchor 词库'}")

    result = anchor_messages_range(
        config,
        trade_date=anchors.trade_date,
        source=_SOURCE_MAP[source_key],
        categories=[cast(MessageCategory, item) for item in categories] or DEFAULT_ANCHOR_CATEGORIES,
        min_classification_confidence=min_classification_confidence,
        start_time=start_time,
        end_time=end_time,
        chunk_hours=chunk_hours,
        limit=limit,
        force=force,
        max_anchors_per_message=max_anchors,
    )
    _echo_anchor_result(result)


def _echo_anchor_result(result: AnchorRangeResult) -> None:
    click.echo(
        f"anchor/messages: chunks={result.chunk_count} empty={result.empty_chunk_count} "
        f"scanned={result.scanned_count} anchored={result.anchored_message_count} "
        f"anchors={result.anchor_count} dictionary={result.dictionary_anchor_count} "
        f"run_id={result.run_id}"
    )
    if result.type_distribution:
        summary = " ".join(f"{key}={value}" for key, value in sorted(result.type_distribution.items()))
        click.echo(f"types: {summary}")
    if result.top_anchors:
        summary = " ".join(f"{key}={value}" for key, value in result.top_anchors.items())
        click.echo(f"top: {summary}")
