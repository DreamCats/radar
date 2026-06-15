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
from radar.core.usecases.stock_evidence_chain import (
    build_stock_evidence_chain,
    refresh_lifecycle_digests,
)
from radar.web.server.schemas import (
    DerivedJobItem,
    LifecycleDigestJobRequest,
    StockEvidenceChainJobRequest,
)

STOCK_EVIDENCE_CHAIN_RUN_KIND = "stock_evidence_chain"
LIFECYCLE_DIGEST_RUN_KIND = "opportunity_lifecycle_digest"
STALE_AFTER = timedelta(hours=12)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-strategy")
_SUBMIT_LOCK = Lock()


def submit_stock_evidence_chain_job(
    config: RadarConfig,
    request: StockEvidenceChainJobRequest,
) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_stock_evidence_chain_runs(config)
        provider_names = _provider_names(config, request.provider_names)
        target = _evidence_chain_target(request, provider_names)
        running = get_running_run(
            config.database_path,
            kind=STOCK_EVIDENCE_CHAIN_RUN_KIND,
            target=target,
        )
        if running is not None:
            return DerivedJobItem(
                job_type="stock_evidence_chain",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=STOCK_EVIDENCE_CHAIN_RUN_KIND,
            target=target,
            metadata=_metadata(request, provider_names),
        )
        _EXECUTOR.submit(_run_stock_evidence_chain_job, config, request, run_id, provider_names)
        return DerivedJobItem(
            job_type="stock_evidence_chain",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_stock_evidence_chain_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=STOCK_EVIDENCE_CHAIN_RUN_KIND,
    )


def submit_lifecycle_digest_job(
    config: RadarConfig,
    request: LifecycleDigestJobRequest,
) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_lifecycle_digest_runs(config)
        provider_names = _provider_names(config, request.provider_names)
        target = _lifecycle_digest_target(request, provider_names)
        running = get_running_run(
            config.database_path,
            kind=LIFECYCLE_DIGEST_RUN_KIND,
            target=target,
        )
        if running is not None:
            return DerivedJobItem(
                job_type="lifecycle_digest",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=LIFECYCLE_DIGEST_RUN_KIND,
            target=target,
            metadata=_lifecycle_metadata(request, provider_names),
        )
        _EXECUTOR.submit(_run_lifecycle_digest_job, config, request, run_id, provider_names)
        return DerivedJobItem(
            job_type="lifecycle_digest",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_lifecycle_digest_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=LIFECYCLE_DIGEST_RUN_KIND,
    )


def _run_stock_evidence_chain_job(
    config: RadarConfig,
    request: StockEvidenceChainJobRequest,
    run_id: str,
    provider_names: list[str | None] | None,
) -> None:
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
            llm_providers=provider_names,
            llm_model=request.model,
            force_llm=request.force_llm,
        )
        metadata = _metadata(request, provider_names)
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


def _run_lifecycle_digest_job(
    config: RadarConfig,
    request: LifecycleDigestJobRequest,
    run_id: str,
    provider_names: list[str | None] | None,
) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "生成机会生命周期摘要"})
        result = refresh_lifecycle_digests(
            config,
            limit=request.limit,
            force=request.force,
            provider_names=provider_names,
            model=request.model,
            llm_workers=request.llm_workers,
        )
        metadata = _lifecycle_metadata(request, provider_names)
        metadata.update(
            {
                "stage": "完成",
                "as_of": result.as_of_time.isoformat() if result.as_of_time else None,
                "scanned_count": result.scanned_count,
                "processable_count": result.processable_count,
                "pending_count": result.pending_count,
                "generated_count": result.generated_count,
                "reused_count": result.reused_count,
                "skipped_count": result.skipped_count,
                "failed_count": result.failed_count,
                "rerun_reason_counts": result.rerun_reason_counts,
            }
        )
        status = (
            "skipped"
            if result.generated_count == 0 and result.reused_count == 0 and result.failed_count == 0
            else "succeeded"
        )
        finish_run(
            config.database_path,
            run_id,
            raw_count=result.processable_count,
            stored_count=result.generated_count + result.reused_count,
            filtered_count=result.failed_count,
            metadata=metadata,
            status=status,
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _evidence_chain_target(
    request: StockEvidenceChainJobRequest,
    provider_names: list[str | None] | None,
) -> str:
    providers = ",".join(provider or "" for provider in provider_names or [])
    return (
        f"stock_evidence_chain:{request.start_time.isoformat()}..{request.end_time.isoformat()}:"
        f"evidence_days={request.evidence_days}:limit={request.limit}:"
        f"llm={int(request.run_llm)}:workers={request.llm_workers}:"
        f"providers={providers}:model={request.model or ''}:force_llm={int(request.force_llm)}"
    )


def _metadata(
    request: StockEvidenceChainJobRequest,
    provider_names: list[str | None] | None,
) -> dict[str, object]:
    metadata = request.model_dump(mode="json")
    metadata["effective_provider_names"] = provider_names
    return metadata


def _lifecycle_digest_target(
    request: LifecycleDigestJobRequest,
    provider_names: list[str | None] | None,
) -> str:
    providers = ",".join(provider or "" for provider in provider_names or [])
    return (
        f"opportunity_lifecycle_digest:limit={request.limit}:force={int(request.force)}:"
        f"workers={request.llm_workers}:providers={providers}:model={request.model or ''}"
    )


def _lifecycle_metadata(
    request: LifecycleDigestJobRequest,
    provider_names: list[str | None] | None,
) -> dict[str, object]:
    metadata = request.model_dump(mode="json")
    metadata["effective_provider_names"] = provider_names
    return metadata


def _provider_names(
    config: RadarConfig,
    requested_names: list[str] | None,
) -> list[str | None] | None:
    if requested_names:
        return requested_names
    return list(config.llm.providers) or None
