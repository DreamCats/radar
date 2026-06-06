from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.usecases.strategy import build_strategy_dashboard, save_cached_strategy_snapshot, summarize_strategy_validation
from radar.core.view_cache import cached_model, cache_key, strategy_dependency_key, strategy_validation_dependency_key
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    DerivedJobResponse,
    StrategyDashboardResponse,
    StrategySnapshotBackfillJobRequest,
    StrategySnapshotSaveRequest,
    StrategySnapshotSaveResponse,
    StrategyValidationResponse,
)
from radar.web.server.strategy_jobs import submit_strategy_backfill_job

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/opportunities", response_model=StrategyDashboardResponse)
def strategy_opportunities(
    days: int = Query(default=30, ge=7, le=180),
    recent_days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=10, ge=1, le=50),
    config: RadarConfig = Depends(get_config),
) -> StrategyDashboardResponse:
    try:
        result = cached_model(
            config.database_path,
            key=cache_key("strategy.opportunities", {"days": days, "recent_days": recent_days, "limit": limit}),
            dependency_key=strategy_dependency_key(config),
            model_type=StrategyDashboardResponse,
            compute=lambda: StrategyDashboardResponse(
                **build_strategy_dashboard(config, days=days, recent_days=recent_days, limit=limit).model_dump()
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/validation", response_model=StrategyValidationResponse)
def strategy_validation(
    window_days: int = Query(default=5, ge=1, le=30),
    benchmark: str = Query(default="000300.SH"),
    source_limit: int = Query(default=8, ge=1, le=30),
    config: RadarConfig = Depends(get_config),
) -> StrategyValidationResponse:
    return cached_model(
        config.database_path,
        key=cache_key(
            "strategy.validation",
            {"window_days": window_days, "benchmark": benchmark, "source_limit": source_limit},
        ),
        dependency_key=strategy_validation_dependency_key(config),
        model_type=StrategyValidationResponse,
        compute=lambda: StrategyValidationResponse(
            **summarize_strategy_validation(
                config,
                window_days=window_days,
                benchmark_ts_code=benchmark,
                source_limit=source_limit,
            ).model_dump()
        ),
    )


@router.post("/snapshots", response_model=StrategySnapshotSaveResponse)
def save_strategy_snapshot(
    request: StrategySnapshotSaveRequest,
    config: RadarConfig = Depends(get_config),
) -> StrategySnapshotSaveResponse:
    result = save_cached_strategy_snapshot(
        config,
        days=request.days,
        recent_days=request.recent_days,
        limit=request.limit,
        force=request.force,
    )
    return StrategySnapshotSaveResponse(**result.model_dump())


@router.post("/snapshots/backfill/jobs", response_model=DerivedJobResponse)
def start_strategy_backfill_job(
    request: StrategySnapshotBackfillJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.start_time and request.end_time and request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    return DerivedJobResponse(items=[submit_strategy_backfill_job(config, request)])
