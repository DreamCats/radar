from __future__ import annotations

from datetime import datetime

import click

from radar.core.config import RadarConfig, load_config


def load_cli_config(ctx: click.Context) -> RadarConfig:
    return load_config(ctx.obj.get("config_dir"))


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return parse_datetime(value)


def parse_datetime(value: str) -> datetime:
    """CLI 支持常用时间格式，避免终端测试时反复补秒。"""

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise click.ClickException(f"时间格式不支持: {value}")
