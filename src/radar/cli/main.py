from __future__ import annotations

from pathlib import Path

import click

from radar import __version__
from radar.cli.aggregate import aggregate
from radar.cli.anchor import anchor
from radar.cli.backtest import backtest
from radar.cli.classify import classify
from radar.cli.dashboard import dashboard
from radar.cli.ingest import ingest
from radar.cli.market import market
from radar.cli.query import query_messages
from radar.cli.strategy import strategy
from radar.cli.test import test_commands


@click.group()
@click.version_option(__version__)
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    envvar="RADAR_CONFIG_DIR",
    help="配置目录，默认读取 ~/.config/radar。",
)
@click.pass_context
def main(ctx: click.Context, config_dir: Path | None) -> None:
    """radar 个人投研工作台。"""

    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


@main.command()
def doctor() -> None:
    """检查 CLI 是否可运行。"""

    # 阶段一先保证入口可用；具体业务命令放在 cli 子模块。
    click.echo("radar CLI ok")


main.add_command(ingest)
main.add_command(anchor)
main.add_command(aggregate)
main.add_command(backtest)
main.add_command(classify)
main.add_command(query_messages)
main.add_command(test_commands)
main.add_command(market)
main.add_command(dashboard)
main.add_command(strategy)
