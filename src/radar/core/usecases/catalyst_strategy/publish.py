from __future__ import annotations

from datetime import datetime
from pathlib import Path

from radar.core.channel import BarkMessage, push_bark
from radar.core.cloud import upload_aly
from radar.core.config import RadarConfig
from radar.core.usecases.catalyst_strategy.models import CatalystStrategyReport
from radar.core.usecases.catalyst_strategy.render import render_report_html


def write_report_html(
    config: RadarConfig,
    report: CatalystStrategyReport,
    *,
    output_path: Path | None = None,
) -> Path:
    path = output_path or _default_output_path(config, report.generated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report_html(report), encoding="utf-8")
    return path


def publish_report_html(config: RadarConfig, local_path: Path, *, generated_at: datetime) -> str:
    remote_path = f"catalyst-strategy/{generated_at:%Y%m%d-%H%M%S}.html"
    return upload_aly(config, local_path, remote_path).url


def notify_report(config: RadarConfig, report: CatalystStrategyReport, url: str) -> None:
    top_names = "、".join(item.stock_name for item in report.stocks[:3]) or "暂无标的"
    push_bark(
        config,
        BarkMessage(
            title="Radar 催化词策略报告",
            subtitle=f"{report.total_stocks} 个标的",
            body=f"{top_names}\n{url}",
            url=url,
            group="radar",
            level="timeSensitive",
        ),
    )


def _default_output_path(config: RadarConfig, generated_at: datetime) -> Path:
    return config.data_dir / "catalyst_strategy" / f"{generated_at:%Y%m%d-%H%M%S}.html"
