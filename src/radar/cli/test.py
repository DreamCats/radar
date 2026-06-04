from __future__ import annotations

import click

from radar.cli.context import load_cli_config
from radar.core.usecases import SmokeResult, test_llm, test_market


@click.group("test")
def test_commands() -> None:
    """测试 core 能力是否可用。"""


@test_commands.command("llm")
@click.option("--provider", "provider_name", help="指定 LLM provider 名称。")
@click.option("--task", help="按任务路由选择 provider。")
@click.option("--model", help="临时覆盖模型名。")
@click.pass_context
def test_llm_command(
    ctx: click.Context,
    provider_name: str | None,
    task: str | None,
    model: str | None,
) -> None:
    """发送一次极短 LLM 请求。"""

    config = load_cli_config(ctx)
    try:
        result = test_llm(config, provider_name=provider_name, task=task, model=model)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_result(result)


@test_commands.command("market")
@click.option("--date", "date_text", help="交易日历日期，格式 YYYYMMDD，默认今天。")
@click.option("--no-cache", is_flag=True, help="跳过本地 market 缓存。")
@click.pass_context
def test_market_command(
    ctx: click.Context,
    date_text: str | None,
    no_cache: bool,
) -> None:
    """请求一次 Tushare 交易日历。"""

    config = load_cli_config(ctx)
    try:
        result = test_market(config, date_text=date_text, use_cache=not no_cache)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_result(result)


def _echo_result(result: SmokeResult) -> None:
    parts = [
        result.capability,
        result.target,
        result.detail,
    ]
    if result.row_count is not None:
        parts.append(f"rows={result.row_count}")
    if result.sample:
        parts.append(f"sample={result.sample}")
    click.echo(" | ".join(parts))
