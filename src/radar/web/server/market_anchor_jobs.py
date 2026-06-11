from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.market import (
    ensure_market_anchors,
    refresh_market_anchor_derivatives,
    refresh_market_theme_normalization,
)
from radar.core.storage import fail_run, fail_stale_runs, finish_run, get_running_run, start_run, update_run_progress
from radar.web.server.schemas import DerivedJobItem, MarketAnchorUpdateRequest

ANCHOR_RUN_KIND = "market_anchor_update"
STALE_AFTER = timedelta(hours=4)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="radar-market-anchor")
_SUBMIT_LOCK = Lock()


def submit_market_anchor_update_job(config: RadarConfig, request: MarketAnchorUpdateRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_market_anchor_runs(config)
        target = _anchor_target(request)
        running = get_running_run(config.database_path, kind=ANCHOR_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(job_type="anchor", run_id=running.run_id, reused_existing=True, status="running")

        run_id = start_run(config.database_path, kind=ANCHOR_RUN_KIND, target=target, metadata=_anchor_metadata(request))
        _EXECUTOR.submit(_run_anchor_job, config, request, run_id)
        return DerivedJobItem(job_type="anchor", run_id=run_id, reused_existing=False, status="running")


def mark_stale_market_anchor_runs(config: RadarConfig) -> int:
    older_than = datetime.now() - STALE_AFTER
    return fail_stale_runs(config.database_path, older_than=older_than, kind=ANCHOR_RUN_KIND)


def _run_anchor_job(config: RadarConfig, request: MarketAnchorUpdateRequest, run_id: str) -> None:
    try:
        update_run_progress(config.database_path, run_id, metadata={"stage": "更新市场 anchor 词库"})
        anchors = ensure_market_anchors(
            config,
            trade_date=request.trade_date,
            min_anchor_count=request.min_anchor_count,
            force=request.force,
        )
        update_run_progress(config.database_path, run_id, metadata={"stage": "重建 anchor 派生表"})
        derivatives = refresh_market_anchor_derivatives(config)
        update_run_progress(config.database_path, run_id, metadata={"stage": "重建主题归一化"})
        themes = refresh_market_theme_normalization(config, rebuild_anchor_derivatives=False)
        metadata = {
            **request.model_dump(mode="json"),
            "stage": "完成",
            "requested_trade_date": request.trade_date,
            "trade_date": anchors.trade_date,
            "market_anchor_refreshed": anchors.refreshed,
            "dictionary_anchor_count": anchors.anchor_count,
            "market_anchor_member_count": anchors.member_count,
            "market_anchor_skipped_reason": anchors.skipped_reason,
            "source_counts": anchors.source_counts,
            "failed_sources": anchors.failed_sources,
            "derived_latest_trade_date": derivatives.latest_trade_date,
            "derived_current_count": derivatives.current_count,
            "derived_span_count": derivatives.span_count,
            "theme_latest_trade_date": themes.latest_trade_date,
            "theme_count": themes.theme_count,
            "theme_source_link_count": themes.source_link_count,
            "theme_membership_count": themes.membership_count,
            "theme_current_stock_count": themes.current_stock_count,
            "theme_covered_stock_count": themes.covered_stock_count,
            "theme_coverage_ratio": themes.coverage_ratio,
            "theme_ambiguous_stock_count": themes.ambiguous_stock_count,
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


def _anchor_target(request: MarketAnchorUpdateRequest) -> str:
    return f"{request.trade_date}:min={request.min_anchor_count}:force={request.force}"


def _anchor_metadata(request: MarketAnchorUpdateRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
