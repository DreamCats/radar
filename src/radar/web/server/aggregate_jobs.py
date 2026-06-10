from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.market_anchors import ensure_market_anchors
from radar.core.models import MessageSource
from radar.core.runs import fail_run, fail_stale_runs, finish_run, get_running_run, start_run, update_run_progress
from radar.core.usecases import refine_aggregate_topics
from radar.web.server.schemas import AggregateRefineRequest, DerivedJobItem, MarketAnchorUpdateRequest

ANCHOR_RUN_KIND = "market_anchor_update"
REFINE_RUN_KIND = "aggregate_refine"
STALE_AFTER = timedelta(hours=4)

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="radar-aggregate")
_SUBMIT_LOCK = Lock()


def submit_market_anchor_update_job(config: RadarConfig, request: MarketAnchorUpdateRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_aggregate_runs(config)
        target = _anchor_target(request)
        running = get_running_run(config.database_path, kind=ANCHOR_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(job_type="anchor", run_id=running.run_id, reused_existing=True, status="running")

        run_id = start_run(config.database_path, kind=ANCHOR_RUN_KIND, target=target, metadata=_anchor_metadata(request))
        _EXECUTOR.submit(_run_anchor_job, config, request, run_id)
        return DerivedJobItem(job_type="anchor", run_id=run_id, reused_existing=False, status="running")


def submit_aggregate_refine_job(config: RadarConfig, request: AggregateRefineRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_aggregate_runs(config)
        target = _refine_target(request)
        running = get_running_run(config.database_path, kind=REFINE_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(job_type="aggregate_refine", run_id=running.run_id, reused_existing=True, status="running")

        run_id = start_run(config.database_path, kind=REFINE_RUN_KIND, target=target, metadata=_refine_metadata(request))
        _EXECUTOR.submit(_run_refine_job, config, request, run_id)
        return DerivedJobItem(job_type="aggregate_refine", run_id=run_id, reused_existing=False, status="running")


def mark_stale_aggregate_runs(config: RadarConfig) -> int:
    older_than = datetime.now() - STALE_AFTER
    return fail_stale_runs(config.database_path, older_than=older_than, kind=ANCHOR_RUN_KIND) + fail_stale_runs(
        config.database_path,
        older_than=older_than,
        kind=REFINE_RUN_KIND,
    )


def _run_anchor_job(config: RadarConfig, request: MarketAnchorUpdateRequest, run_id: str) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "更新市场 anchor 词库"})
        anchors = ensure_market_anchors(
            config,
            trade_date=request.trade_date,
            min_anchor_count=request.min_anchor_count,
            force=request.force,
        )
        metadata = {
            **request.model_dump(mode="json"),
            "stage": "更新市场 anchor 词库",
            "requested_trade_date": request.trade_date,
            "trade_date": anchors.trade_date,
            "market_anchor_refreshed": anchors.refreshed,
            "dictionary_anchor_count": anchors.anchor_count,
            "market_anchor_member_count": anchors.member_count,
            "market_anchor_skipped_reason": anchors.skipped_reason,
            "source_counts": anchors.source_counts,
            "failed_sources": anchors.failed_sources,
        }
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if anchors.skipped_reason and not anchors.refreshed else "succeeded",
            raw_count=anchors.member_count,
            stored_count=anchors.anchor_count,
            filtered_count=len(anchors.failed_sources),
            metadata=metadata,
        )
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)


def _run_refine_job(config: RadarConfig, request: AggregateRefineRequest, run_id: str) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "准备 anchor 词库"})
        anchor_trade_date = _ensure_job_anchor_trade_date(config, requested_trade_date=request.trade_date, run_id=run_id)
        refine_aggregate_topics(
            config,
            trade_date=anchor_trade_date,
            source=_SOURCE_MAP[request.source],
            categories=request.categories,
            min_classification_confidence=request.min_classification_confidence,
            start_time=request.start_time,
            end_time=request.end_time,
            min_messages=request.min_messages,
            candidate_limit=request.candidate_limit,
            evidence_limit=request.evidence_limit,
            batch_size=request.batch_size,
            max_concurrency=request.max_concurrency,
            provider_name=request.provider_name,
            provider_names=request.provider_names,
            force=request.force,
            run_id=run_id,
        )
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)


def _ensure_job_anchor_trade_date(config: RadarConfig, *, requested_trade_date: str, run_id: str) -> str:
    anchors = ensure_market_anchors(config, trade_date=requested_trade_date, min_anchor_count=100)
    anchor_trade_date = anchors.trade_date if anchors is not None else requested_trade_date
    update_run_progress(
        config.database_path,
        run_id,
        metadata={
            "stage": "准备 anchor 词库",
            "requested_trade_date": requested_trade_date,
            "trade_date": anchor_trade_date,
            "market_anchor_refreshed": anchors.refreshed if anchors is not None else None,
            "dictionary_anchor_count": anchors.anchor_count if anchors is not None else None,
            "market_anchor_skipped_reason": getattr(anchors, "skipped_reason", None),
        },
    )
    return anchor_trade_date


def _anchor_target(request: MarketAnchorUpdateRequest) -> str:
    return f"{request.trade_date}:min={request.min_anchor_count}:force={request.force}"


def _refine_target(request: AggregateRefineRequest) -> str:
    return (
        f"{request.source}:{request.trade_date}:{','.join(request.categories)}:"
        f"{request.start_time.isoformat()}..{request.end_time.isoformat()}"
        f"|candidates={request.candidate_limit}|batch={request.batch_size}"
    )


def _anchor_metadata(request: MarketAnchorUpdateRequest) -> dict[str, object]:
    return request.model_dump(mode="json")


def _refine_metadata(request: AggregateRefineRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
