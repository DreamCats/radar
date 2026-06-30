from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.storage import fail_run, fail_stale_runs, finish_run, get_running_run, start_run
from radar.core.storage.report_store import save_catalyst_valuation_report
from radar.core.usecases.catalyst_valuation_report import run_catalyst_valuation_report
from radar.web.server.schemas import CatalystValuationReportJobRequest, DerivedJobItem

CATALYST_VALUATION_REPORT_RUN_KIND = "catalyst_valuation_report"
STALE_AFTER = timedelta(hours=3)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-catalyst-valuation-report")
_SUBMIT_LOCK = Lock()


def submit_catalyst_valuation_report_job(config: RadarConfig, request: CatalystValuationReportJobRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_catalyst_valuation_report_runs(config)
        target = _target(request)
        running = get_running_run(config.database_path, kind=CATALYST_VALUATION_REPORT_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="catalyst_valuation_report",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=CATALYST_VALUATION_REPORT_RUN_KIND,
            target=target,
            metadata=_metadata(request) | {"stage": "生成催化估值线索报告"},
        )
        _EXECUTOR.submit(_run_catalyst_valuation_report_job, config, request, run_id)
        return DerivedJobItem(
            job_type="catalyst_valuation_report",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_catalyst_valuation_report_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=CATALYST_VALUATION_REPORT_RUN_KIND,
    )


def _run_catalyst_valuation_report_job(config: RadarConfig, request: CatalystValuationReportJobRequest, run_id: str) -> None:
    try:
        result = run_catalyst_valuation_report(
            config,
            start_time=request.start_time,
            end_time=request.end_time,
            limit=request.limit,
            max_stocks=request.max_stocks,
            publish=request.publish,
            notify=request.notify,
        )
        report = result.report
        status = "skipped" if report.total_stocks == 0 else "succeeded"
        if result.bark_error and status == "succeeded":
            status = "partial_failed"
        archived = save_catalyst_valuation_report(
            config.reports_database_path,
            request=_metadata(request),
            result=result,
            run_id=run_id,
            status=status,
        )
        finish_run(
            config.database_path,
            run_id,
            status=status,
            raw_count=report.total_feed_items,
            stored_count=report.total_stocks,
            filtered_count=max(report.total_candidate_stocks - report.total_stocks, 0),
            error_message=f"Bark 通知失败: {result.bark_error}" if result.bark_error else None,
            metadata=_metadata(request)
            | {
                "stage": "完成",
                "total_feed_items": report.total_feed_items,
                "total_candidate_stocks": report.total_candidate_stocks,
                "total_stocks": report.total_stocks,
                "local_html_path": str(result.local_html_path),
                "published_url": result.published_url,
                "report_id": archived.report_id,
                "bark_sent": result.bark_sent,
                "bark_error": result.bark_error,
            },
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _target(request: CatalystValuationReportJobRequest) -> str:
    publish = "publish" if request.publish else "local"
    notify = "notify" if request.notify else "silent"
    return f"{request.start_time.isoformat()}..{request.end_time.isoformat()}:{publish}:{notify}"


def _metadata(request: CatalystValuationReportJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json", exclude_none=True)
