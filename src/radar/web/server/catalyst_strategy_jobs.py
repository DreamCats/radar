from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.storage import fail_run, fail_stale_runs, finish_run, get_running_run, start_run
from radar.core.usecases.catalyst_strategy import run_catalyst_strategy_report
from radar.web.server.schemas import CatalystStrategyJobRequest, DerivedJobItem

CATALYST_STRATEGY_RUN_KIND = "catalyst_strategy_report"
STALE_AFTER = timedelta(hours=3)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-catalyst-strategy")
_SUBMIT_LOCK = Lock()


def submit_catalyst_strategy_job(config: RadarConfig, request: CatalystStrategyJobRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_catalyst_strategy_runs(config)
        target = _target(request)
        running = get_running_run(config.database_path, kind=CATALYST_STRATEGY_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="catalyst_strategy",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=CATALYST_STRATEGY_RUN_KIND,
            target=target,
            metadata=_metadata(request) | {"stage": "生成催化策略报告"},
        )
        _EXECUTOR.submit(_run_catalyst_strategy_job, config, request, run_id)
        return DerivedJobItem(
            job_type="catalyst_strategy",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_catalyst_strategy_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=CATALYST_STRATEGY_RUN_KIND,
    )


def _run_catalyst_strategy_job(config: RadarConfig, request: CatalystStrategyJobRequest, run_id: str) -> None:
    try:
        result = run_catalyst_strategy_report(
            config,
            start_time=request.start_time,
            end_time=request.end_time,
            limit=request.limit,
            max_stocks=request.max_stocks,
            llm_concurrency=request.llm_concurrency,
            provider_name=request.provider_name,
            model=request.model,
            publish=request.publish,
            notify=request.notify,
        )
        report = result.report
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if report.total_stocks == 0 else "succeeded",
            raw_count=report.total_feed_items,
            stored_count=report.total_stocks,
            filtered_count=max(report.total_feed_items - report.total_stocks, 0),
            metadata=_metadata(request)
            | {
                "stage": "完成",
                "total_feed_items": report.total_feed_items,
                "total_stocks": report.total_stocks,
                "local_html_path": str(result.local_html_path),
                "published_url": result.published_url,
                "bark_sent": result.bark_sent,
            },
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _target(request: CatalystStrategyJobRequest) -> str:
    publish = "publish" if request.publish else "local"
    notify = "notify" if request.notify else "silent"
    return f"{request.start_time.isoformat()}..{request.end_time.isoformat()}:{publish}:{notify}"


def _metadata(request: CatalystStrategyJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
