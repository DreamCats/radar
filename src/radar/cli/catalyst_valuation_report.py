from __future__ import annotations

import json
from pathlib import Path

import click

from radar.cli.context import load_cli_config, parse_optional_datetime
from radar.core.usecases.catalyst_valuation_report import (
    CatalystValuationReportRunResult,
    run_catalyst_valuation_report,
)


@click.group("catalyst-valuation-report")
def catalyst_valuation_report() -> None:
    """基于催化词线索生成估值证据报告。"""


@catalyst_valuation_report.command("run")
@click.option("--start", "start_text", help="开始时间。")
@click.option("--end", "end_text", help="结束时间，默认当前时间。")
@click.option("--hours", type=click.IntRange(1, 168), default=24, show_default=True, help="未传 start 时回看小时数。")
@click.option("--limit", type=click.IntRange(1, 200), default=200, show_default=True, help="读取的催化词条目上限。")
@click.option("--max-stocks", type=click.IntRange(1, 50), default=12, show_default=True, help="最多分析标的数。")
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False), help="本地 HTML 输出路径。")
@click.option("--publish", is_flag=True, help="上传 HTML 到 Aly。")
@click.option("--notify", is_flag=True, help="上传后发送 Bark 通知；必须同时传 --publish。")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.pass_context
def run_command(
    ctx: click.Context,
    start_text: str | None,
    end_text: str | None,
    hours: int,
    limit: int,
    max_stocks: int,
    output_path: Path | None,
    publish: bool,
    notify: bool,
    output_format: str,
) -> None:
    """扫描最近催化词消息，按标的生成 HTML 估值线索报告。"""

    if notify and not publish:
        raise click.ClickException("--notify 需要同时传 --publish")
    config = load_cli_config(ctx)
    try:
        result = run_catalyst_valuation_report(
            config,
            start_time=parse_optional_datetime(start_text),
            end_time=parse_optional_datetime(end_text),
            hours=hours,
            limit=limit,
            max_stocks=max_stocks,
            output_path=output_path,
            publish=publish,
            notify=notify,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_result(result, output_format=output_format)


def _echo_result(result: CatalystValuationReportRunResult, *, output_format: str) -> None:
    if output_format == "json":
        click.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return
    click.echo(
        "catalyst-valuation-report: "
        f"stocks={result.report.total_stocks} "
        f"feed_items={result.report.total_feed_items} "
        f"html={result.local_html_path}"
    )
    if result.published_url:
        click.echo(f"url={result.published_url}")
    if result.bark_sent:
        click.echo("bark=sent")
    elif result.bark_error:
        click.echo(f"bark=failed error={result.bark_error}")
