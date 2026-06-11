from __future__ import annotations

import click

from radar.cli.context import load_cli_config
from radar.core.market import (
    ensure_market_anchors,
    refresh_market_anchor_derivatives,
    refresh_market_anchors,
)
from radar.core.market import refresh_market_theme_normalization


@click.group("market")
def market() -> None:
    """市场数据和 anchor 词库。"""


@market.group("anchors")
def anchors() -> None:
    """管理市场 anchor 词库。"""


@market.group("themes")
def themes() -> None:
    """管理自动主题归一化层。"""


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


@anchors.command("rebuild-derived")
@click.pass_context
def rebuild_anchor_derivatives_command(ctx: click.Context) -> None:
    """从本地 raw anchor 快照重建 latest/current 和区间压缩表。"""

    config = load_cli_config(ctx)
    try:
        result = refresh_market_anchor_derivatives(config)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        "market/anchors/derived: "
        f"latest_trade_date={result.latest_trade_date or '-'} "
        f"current={result.current_count} spans={result.span_count}"
    )


@themes.command("rebuild")
@click.option("--skip-anchor-derived", is_flag=True, help="不先重建 current/spans 派生表。")
@click.pass_context
def rebuild_themes_command(ctx: click.Context, skip_anchor_derived: bool) -> None:
    """基于 anchor 派生表重建自动主题归一化层。"""

    config = load_cli_config(ctx)
    try:
        result = refresh_market_theme_normalization(
            config,
            rebuild_anchor_derivatives=not skip_anchor_derived,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        "market/themes: "
        f"latest_trade_date={result.latest_trade_date or '-'} "
        f"themes={result.theme_count} links={result.source_link_count} "
        f"memberships={result.membership_count} "
        f"covered={result.covered_stock_count}/{result.current_stock_count} "
        f"coverage={result.coverage_ratio:.1%} ambiguous={result.ambiguous_stock_count}"
    )
