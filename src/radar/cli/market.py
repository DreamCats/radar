from __future__ import annotations

import click

from radar.cli.context import load_cli_config
from radar.core.market_anchors import ensure_market_anchors, refresh_market_anchors


@click.group("market")
def market() -> None:
    """市场数据和 anchor 词库。"""


@market.group("anchors")
def anchors() -> None:
    """管理市场 anchor 词库。"""


@anchors.command("refresh")
@click.option("--trade-date", required=True, help="交易日，格式 YYYYMMDD。")
@click.option("--no-cache", is_flag=True, help="跳过 Tushare 原始响应缓存。")
@click.pass_context
def refresh_anchors_command(ctx: click.Context, trade_date: str, no_cache: bool) -> None:
    """刷新指定交易日的概念、题材、行业 anchor 词库。"""

    config = load_cli_config(ctx)
    try:
        result = refresh_market_anchors(config, trade_date=trade_date, use_cache=not no_cache)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        "market/anchors: "
        f"trade_date={result.trade_date} anchors={result.anchor_count} members={result.member_count} "
        f"sources={result.source_counts}"
    )
    if result.failed_sources:
        click.echo(f"failed_sources={result.failed_sources}")


@anchors.command("ensure")
@click.option("--trade-date", required=True, help="交易日，格式 YYYYMMDD。")
@click.option("--min-anchors", default=100, show_default=True, help="已有 anchor 数达到该值则跳过刷新。")
@click.option("--force", is_flag=True, help="强制刷新，即使本地已有词库。")
@click.option("--no-cache", is_flag=True, help="跳过 Tushare 原始响应缓存。")
@click.pass_context
def ensure_anchors_command(
    ctx: click.Context,
    trade_date: str,
    min_anchors: int,
    force: bool,
    no_cache: bool,
) -> None:
    """确保指定交易日存在 anchor 词库；已有数据时直接跳过。"""

    config = load_cli_config(ctx)
    try:
        result = ensure_market_anchors(
            config,
            trade_date=trade_date,
            min_anchor_count=min_anchors,
            force=force,
            use_cache=not no_cache,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    status = "refreshed" if result.refreshed else "skipped"
    click.echo(
        "market/anchors: "
        f"trade_date={result.trade_date} status={status} "
        f"anchors={result.anchor_count} members={result.member_count}"
    )
    if result.skipped_reason:
        click.echo(f"reason={result.skipped_reason}")
    if result.source_counts:
        click.echo(f"sources={result.source_counts}")
    if result.failed_sources:
        click.echo(f"failed_sources={result.failed_sources}")
