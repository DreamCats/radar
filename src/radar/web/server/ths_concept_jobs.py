from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.storage import (
    fail_run,
    fail_stale_runs,
    finish_run,
    get_running_run,
    start_run,
    update_run_progress,
)
from radar.core.tushare import refresh_ths_concepts
from radar.web.server.job_locks import WRITE_JOB_LOCK
from radar.web.server.schemas import DerivedJobItem, ThsConceptRefreshRequest

THS_CONCEPT_REFRESH_RUN_KIND = "market_ths_concept_refresh"
THS_CONCEPT_REFRESH_TARGET = "ths_concepts:incremental"
STALE_AFTER = timedelta(hours=4)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-ths-concepts")
_SUBMIT_LOCK = Lock()


def submit_ths_concept_refresh_job(config: RadarConfig, request: ThsConceptRefreshRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_ths_concept_refresh_runs(config)
        running = get_running_run(
            config.database_path,
            kind=THS_CONCEPT_REFRESH_RUN_KIND,
            target=THS_CONCEPT_REFRESH_TARGET,
        )
        if running is not None:
            return DerivedJobItem(
                job_type="ths_concept_refresh",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=THS_CONCEPT_REFRESH_RUN_KIND,
            target=THS_CONCEPT_REFRESH_TARGET,
            metadata=_metadata(request),
        )
        _EXECUTOR.submit(_run_ths_concept_refresh_job, config, request, run_id)
        return DerivedJobItem(
            job_type="ths_concept_refresh",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_ths_concept_refresh_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=THS_CONCEPT_REFRESH_RUN_KIND,
    )


def _run_ths_concept_refresh_job(config: RadarConfig, request: ThsConceptRefreshRequest, run_id: str) -> None:
    with WRITE_JOB_LOCK:
        try:
            result = refresh_ths_concepts(
                config,
                force=request.force,
                progress=lambda metadata: update_run_progress(
                    config.database_path,
                    run_id,
                    raw_count=int(metadata.get("concept_count") or 0),
                    stored_count=int(metadata.get("member_row_count") or 0),
                    filtered_count=int(metadata.get("skipped_member_count") or 0),
                    metadata=_metadata(request) | metadata,
                ),
            )
            finish_run(
                config.database_path,
                run_id,
                raw_count=result.concept_count,
                stored_count=result.member_row_count,
                filtered_count=result.skipped_member_count,
                metadata=_metadata(request) | result.metadata(),
            )
        except BaseException as exc:
            fail_run(config.database_path, run_id, exc)


def _metadata(request: ThsConceptRefreshRequest) -> dict[str, object]:
    return request.model_dump(mode="json") | {"mode": "force" if request.force else "incremental"}
