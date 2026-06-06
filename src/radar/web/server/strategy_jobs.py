from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.runs import fail_run, fail_stale_runs, finish_run, get_running_run, start_run, update_run_progress
from radar.core.usecases.strategy.snapshots import backfill_strategy_snapshot_returns
from radar.web.server.schemas import DerivedJobItem, StrategySnapshotBackfillJobRequest

STRATEGY_BACKFILL_RUN_KIND = "strategy_snapshot_backfill"
STALE_AFTER = timedelta(hours=12)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-strategy")
_SUBMIT_LOCK = Lock()


def submit_strategy_backfill_job(config: RadarConfig, request: StrategySnapshotBackfillJobRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_strategy_runs(config)
        target = _target(request)
        running = get_running_run(config.database_path, kind=STRATEGY_BACKFILL_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="strategy_backfill",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(config.database_path, kind=STRATEGY_BACKFILL_RUN_KIND, target=target, metadata=_metadata(request))
        _EXECUTOR.submit(_run_strategy_backfill_job, config, request, run_id)
        return DerivedJobItem(
            job_type="strategy_backfill",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_strategy_runs(config: RadarConfig) -> int:
    return fail_stale_runs(config.database_path, older_than=datetime.now() - STALE_AFTER, kind=STRATEGY_BACKFILL_RUN_KIND)


def _run_strategy_backfill_job(config: RadarConfig, request: StrategySnapshotBackfillJobRequest, run_id: str) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "回填已有策略快照"})
        backfill = backfill_strategy_snapshot_returns(
            config,
            windows=request.windows,
            benchmark_ts_code=request.benchmark_ts_code,
            snapshot_start_time=request.start_time,
            snapshot_end_time=request.end_time,
        )
        metadata = _metadata(request)
        metadata.update(
            {
                "stage": "完成",
                "snapshot_count": backfill.snapshot_count,
                "refreshed_count": backfill.refreshed_count,
                "pending_count": backfill.pending_count,
                "missing_price_count": backfill.missing_price_count,
                "failed_count": backfill.failed_count,
            }
        )
        finish_run(
            config.database_path,
            run_id,
            raw_count=backfill.stock_count,
            stored_count=backfill.refreshed_count,
            filtered_count=backfill.pending_count + backfill.missing_price_count + backfill.failed_count,
            metadata=metadata,
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _target(request: StrategySnapshotBackfillJobRequest) -> str:
    windows = ",".join(str(item) for item in sorted(set(request.windows)))
    start = request.start_time.isoformat() if request.start_time else "*"
    end = request.end_time.isoformat() if request.end_time else "*"
    return f"opportunity_signal:{start}..{end}:windows={windows}:benchmark={request.benchmark_ts_code}"


def _metadata(request: StrategySnapshotBackfillJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
