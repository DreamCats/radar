from __future__ import annotations

import click

from radar import __version__


@click.group()
@click.version_option(__version__)
def main() -> None:
    """radar 个人投研工作台。"""


@main.command()
def doctor() -> None:
    """检查 CLI 是否可运行。"""

    # 阶段一先保证入口可用；真实 fetch/list/stats 后续都应调用 core。
    click.echo("radar CLI ok")
