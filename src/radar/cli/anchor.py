from __future__ import annotations

import click

from radar.cli.context import load_cli_config
from radar.core.market import ensure_market_anchors


@click.group()
def anchor() -> None:
    """更新市场 anchor 词库。"""


@anchor.command("update")
@click.option("--trade-date", required=True, help="anchor 词库交易日，格式 YYYYMMDD。")
@click.option("--force", is_flag=True, help="强制刷新 market_anchors 和 market_anchor_members。")
@click.option("--min-anchors", default=100, show_default=True, help="已有 anchor 数达到该值则跳过刷新。")
@click.pass_context
def anchor_update_command(ctx: click.Context, trade_date: str, force: bool, min_anchors: int) -> None:
    """增量更新市场 anchor 词库，不扫描消息库。"""

    result = ensure_market_anchors(
        load_cli_config(ctx),
        trade_date=trade_date,
        min_anchor_count=min_anchors,
        force=force,
    )
    status = "refreshed" if result.refreshed else "skipped"
    click.echo(
        "anchor/update: "
        f"trade_date={result.trade_date} requested={result.requested_trade_date or trade_date} "
        f"status={status} anchors={result.anchor_count} members={result.member_count}"
    )
    if result.skipped_reason:
        click.echo(f"reason={result.skipped_reason}")
    if result.failed_sources:
        failures = " ".join(f"{key}={value}" for key, value in sorted(result.failed_sources.items()))
        click.echo(f"failed_sources: {failures}")
