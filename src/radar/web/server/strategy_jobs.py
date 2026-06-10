from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.runs import fail_run, fail_stale_runs, finish_run, get_running_run, start_run, update_run_progress
from radar.core.usecases.stock_evidence_chain import build_stock_evidence_chain
from radar.core.usecases.strategy.snapshots import backfill_strategy_snapshot_returns
from radar.web.server.schemas import DerivedJobItem, StockEvidenceChainJobRequest, StrategySnapshotBackfillJobRequest

STRATEGY_BACKFILL_RUN_KIND = "strategy_snapshot_backfill"
STOCK_EVIDENCE_CHAIN_RUN_KIND = "stock_evidence_chain"
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


def submit_stock_evidence_chain_job(config: RadarConfig, request: StockEvidenceChainJobRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_strategy_runs(config, kind=STOCK_EVIDENCE_CHAIN_RUN_KIND)
        target = _evidence_chain_target(request)
        running = get_running_run(config.database_path, kind=STOCK_EVIDENCE_CHAIN_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="stock_evidence_chain",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(config.database_path, kind=STOCK_EVIDENCE_CHAIN_RUN_KIND, target=target, metadata=_metadata(request))
        _EXECUTOR.submit(_run_stock_evidence_chain_job, config, request, run_id)
        return DerivedJobItem(
            job_type="stock_evidence_chain",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_strategy_runs(config: RadarConfig, *, kind: str = STRATEGY_BACKFILL_RUN_KIND) -> int:
    return fail_stale_runs(config.database_path, older_than=datetime.now() - STALE_AFTER, kind=kind)


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


def _run_stock_evidence_chain_job(config: RadarConfig, request: StockEvidenceChainJobRequest, run_id: str) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "构建个股证据链"})
        result = build_stock_evidence_chain(
            config,
            as_of=request.end_time,
            window_start=request.start_time,
            evidence_days=request.evidence_days,
            limit=request.limit,
            run_llm=request.run_llm,
            llm_workers=request.llm_workers,
            llm_providers=request.provider_names,
            llm_model=request.model,
            force_llm=request.force_llm,
        )
        metadata = _metadata(request)
        metadata.update(
            {
                "stage": "完成",
                "as_of": result.as_of.isoformat(),
                "window_start": result.window_start.isoformat(),
                "evidence_start": result.evidence_start.isoformat(),
                "indexed_messages": result.indexed_messages,
                "mention_count": result.mention_count,
                "candidate_count": result.candidate_count,
                "judged_count": result.judged_count,
                "reused_count": result.reused_count,
                "failed_count": result.failed_count,
            }
        )
        finish_run(
            config.database_path,
            run_id,
            raw_count=result.indexed_messages,
            stored_count=result.candidate_count,
            filtered_count=result.failed_count,
            metadata=metadata,
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _target(request: StrategySnapshotBackfillJobRequest) -> str:
    windows = ",".join(str(item) for item in sorted(set(request.windows)))
    start = request.start_time.isoformat() if request.start_time else "*"
    end = request.end_time.isoformat() if request.end_time else "*"
    return f"opportunity_signal:{start}..{end}:windows={windows}:benchmark={request.benchmark_ts_code}"


def _evidence_chain_target(request: StockEvidenceChainJobRequest) -> str:
    providers = ",".join(request.provider_names or [])
    return (
        f"stock_evidence_chain:{request.start_time.isoformat()}..{request.end_time.isoformat()}:"
        f"evidence_days={request.evidence_days}:limit={request.limit}:"
        f"llm={int(request.run_llm)}:workers={request.llm_workers}:"
        f"providers={providers}:model={request.model or ''}:force_llm={int(request.force_llm)}"
    )


def _metadata(request: StrategySnapshotBackfillJobRequest | StockEvidenceChainJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
