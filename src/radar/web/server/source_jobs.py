from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.runs import fail_run, fail_stale_runs, finish_run, get_running_run, start_run, update_run_progress
from radar.core.usecases.source import extract_source_structures, scan_source_signals
from radar.web.server.schemas import DerivedJobItem, SourceRadarJobRequest

SOURCE_RADAR_RUN_KIND = "source_radar_snapshot"
STALE_AFTER = timedelta(hours=12)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-source")
_SUBMIT_LOCK = Lock()


def submit_source_radar_job(config: RadarConfig, request: SourceRadarJobRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_source_runs(config)
        target = _target(request)
        running = get_running_run(config.database_path, kind=SOURCE_RADAR_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(job_type="source_radar", run_id=running.run_id, reused_existing=True, status="running")

        run_id = start_run(config.database_path, kind=SOURCE_RADAR_RUN_KIND, target=target, metadata=_metadata(request))
        _EXECUTOR.submit(_run_source_radar_job, config, request, run_id)
        return DerivedJobItem(job_type="source_radar", run_id=run_id, reused_existing=False, status="running")


def mark_stale_source_runs(config: RadarConfig) -> int:
    return fail_stale_runs(config.database_path, older_than=datetime.now() - STALE_AFTER, kind=SOURCE_RADAR_RUN_KIND)


def _run_source_radar_job(config: RadarConfig, request: SourceRadarJobRequest, run_id: str) -> None:
    totals = {
        "day_count": 0,
        "completed_day_count": 0,
        "scanned_count": 0,
        "extracted_count": 0,
        "inserted_count": 0,
        "failed_llm_batches": 0,
        "scan_candidate_count": 0,
        "snapshot_count": 0,
    }
    try:
        days = _day_windows(request.start_time, request.end_time)
        totals["day_count"] = len(days)
        update_run_progress(config.database_path, run_id, metadata=_metadata(request) | totals | {"stage": "准备源头雷达快照"})

        for index, (day_start, day_end) in enumerate(days, start=1):
            stage_prefix = f"{day_start.date().isoformat()} ({index}/{len(days)})"
            update_run_progress(config.database_path, run_id, metadata=totals | {"stage": f"{stage_prefix} 抽取结构"})
            extract = extract_source_structures(
                config,
                start_time=day_start,
                end_time=day_end,
                limit=request.per_day_limit,
                force=request.force,
                batch_size=request.batch_size,
                max_concurrency=request.max_concurrency,
                provider_name=request.provider_name,
                provider_names=request.provider_names,
            )
            totals["scanned_count"] += extract.scanned_count
            totals["extracted_count"] += extract.extracted_count
            totals["inserted_count"] += extract.inserted_count
            totals["failed_llm_batches"] += extract.failed_llm_batches

            update_run_progress(config.database_path, run_id, metadata=totals | {"stage": f"{stage_prefix} 扫描快照"})
            scan = scan_source_signals(
                config,
                start_time=day_start,
                end_time=day_end,
                as_of_time=day_end,
                lookback_days=request.lookback_days,
                limit=request.scan_limit,
                save_snapshot=True,
            )
            totals["scan_candidate_count"] += scan.candidate_count
            totals["snapshot_count"] += len(scan.candidates)
            totals["completed_day_count"] += 1
            update_run_progress(
                config.database_path,
                run_id,
                raw_count=totals["scanned_count"],
                stored_count=totals["inserted_count"],
                filtered_count=totals["failed_llm_batches"],
                metadata=totals | {"stage": f"{stage_prefix} 完成"},
            )

        finish_run(
            config.database_path,
            run_id,
            raw_count=totals["scanned_count"],
            stored_count=totals["inserted_count"],
            filtered_count=totals["failed_llm_batches"],
            metadata=_metadata(request) | totals | {"stage": "完成"},
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _day_windows(start_time: datetime, end_time: datetime) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    current = start_time
    while current < end_time:
        day_end = datetime.combine(current.date(), time.max).replace(microsecond=0)
        clipped_end = min(day_end, end_time)
        if clipped_end > current:
            windows.append((current, clipped_end))
        current = datetime.combine(current.date() + timedelta(days=1), time.min)
    return windows


def _target(request: SourceRadarJobRequest) -> str:
    return (
        f"{request.start_time.isoformat()}..{request.end_time.isoformat()}"
        f"|limit={request.per_day_limit}|lookback={request.lookback_days}|scan={request.scan_limit}|force={request.force}"
    )


def _metadata(request: SourceRadarJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
