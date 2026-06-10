from __future__ import annotations

from fastapi import APIRouter, Depends

from radar.core.config import RadarConfig
from radar.core.dashboard import DashboardSummaryPayload, build_dashboard_summary_payload
from radar.core.runs import list_runs
from radar.core.view_cache import cached_model, cache_key, cleanup_cache, dashboard_dependency_key
from radar.web.server.aggregate_jobs import mark_stale_aggregate_runs
from radar.web.server.backtest_jobs import mark_stale_backtest_runs
from radar.web.server.classify_jobs import mark_stale_classify_runs
from radar.web.server.deps import get_config
from radar.web.server.ingest_jobs import mark_stale_ingest_runs
from radar.web.server.schemas import DashboardSummaryResponse
from radar.web.server.strategy_jobs import mark_stale_stock_evidence_chain_runs

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(config: RadarConfig = Depends(get_config)) -> DashboardSummaryResponse:
    dependency_key = dashboard_dependency_key(config)
    payload = cached_model(
        config.database_path,
        key=cache_key("dashboard.summary", {"version": 2}),
        dependency_key=dependency_key,
        model_type=DashboardSummaryPayload,
        compute=lambda: build_dashboard_summary_payload(config),
    )
    cleanup_cache(config.database_path)
    return DashboardSummaryResponse(**payload.model_dump(), runs=_recent_runs(config))


def _recent_runs(config: RadarConfig):
    mark_stale_ingest_runs(config)
    mark_stale_classify_runs(config)
    mark_stale_aggregate_runs(config)
    mark_stale_backtest_runs(config)
    mark_stale_stock_evidence_chain_runs(config)
    return list_runs(config.database_path, limit=20)
