from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.usecases.catalyst_valuation_report.collect import collect_catalyst_valuation_contexts
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationReport,
    CatalystValuationReportRunResult,
)
from radar.core.usecases.catalyst_valuation_report.publish import (
    notify_report,
    publish_report_html,
    write_report_html,
)


def run_catalyst_valuation_report(
    config: RadarConfig,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    hours: int = 24,
    limit: int = 200,
    max_stocks: int = 12,
    output_path: Path | None = None,
    publish: bool = False,
    notify: bool = False,
) -> CatalystValuationReportRunResult:
    end = end_time or datetime.now()
    start = start_time or (end - timedelta(hours=hours))
    contexts, total_feed_items, total_candidate_stocks = collect_catalyst_valuation_contexts(
        config,
        start_time=start,
        end_time=end,
        limit=limit,
        max_stocks=max_stocks,
    )
    report = CatalystValuationReport(
        generated_at=datetime.now(),
        start_time=start,
        end_time=end,
        total_feed_items=total_feed_items,
        total_candidate_stocks=total_candidate_stocks,
        total_stocks=len(contexts),
        stocks=contexts,
    )
    local_path = write_report_html(config, report, output_path=output_path)
    should_publish = publish and report.total_stocks > 0
    should_notify = notify and report.total_stocks > 0
    url = publish_report_html(config, local_path, generated_at=report.generated_at) if should_publish else None
    if should_notify:
        if not url:
            raise ValueError("notify=true 需要同时 publish=true，确保 Bark 可以打开公网 URL")
        notify_report(config, report, url)
    return CatalystValuationReportRunResult(
        report=report,
        local_html_path=local_path,
        published_url=url,
        bark_sent=should_notify,
    )
