from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.db import migrate_message_db
from radar.core.store import connect
from radar.core.usecases.source.storage import list_latest_source_signal_snapshots
from radar.core.usecases.source.validation import summarize_source_signal_validation
from radar.core.usecases.strategy import (
    build_strategy_dashboard,
    get_strategy_stock_chart,
    save_cached_strategy_snapshot,
    summarize_lead_signals,
    summarize_strategy_validation,
)
from radar.core.view_cache import (
    cached_model,
    cache_key,
    source_radar_dependency_key,
    strategy_dependency_key,
    strategy_validation_dependency_key,
)
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    DerivedJobResponse,
    LeadSignalResponse,
    SourceRadarSnapshotResponse,
    SourceRadarValidationResponse,
    StrategyDashboardResponse,
    StrategyStockChartResponse,
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


@router.get("/stocks/{ts_code}/chart", response_model=StrategyStockChartResponse)
def strategy_stock_chart(
    ts_code: str,
    days: int = Query(default=120, ge=1, le=260),
    config: RadarConfig = Depends(get_config),
) -> StrategyStockChartResponse:
    try:
        result = get_strategy_stock_chart(config, ts_code=ts_code, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyStockChartResponse(**result.model_dump())


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


@router.get("/lead-signals", response_model=LeadSignalResponse)
def strategy_lead_signals(
    as_of_date: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=20, ge=1, le=100),
    source_limit: int = Query(default=12, ge=1, le=50),
    benchmark: str = Query(default="000300.SH"),
    message_day_max_pct: float = Query(default=2.0, ge=-30, le=30),
    strong_return_pct: float = Query(default=3.0, ge=-30, le=30),
    limit_like_pct: float = Query(default=9.5, ge=0, le=30),
    config: RadarConfig = Depends(get_config),
) -> LeadSignalResponse:
    try:
        return cached_model(
            config.database_path,
            key=cache_key(
                "strategy.lead_signals.v1",
                {
                    "days": days,
                    "as_of_date": as_of_date,
                    "limit": limit,
                    "source_limit": source_limit,
                    "benchmark": benchmark,
                    "message_day_max_pct": message_day_max_pct,
                    "strong_return_pct": strong_return_pct,
                    "limit_like_pct": limit_like_pct,
                },
            ),
            dependency_key=strategy_dependency_key(config),
            model_type=LeadSignalResponse,
            compute=lambda: LeadSignalResponse(
                **summarize_lead_signals(
                    config,
                    as_of_date=as_of_date,
                    days=days,
                    limit=limit,
                    source_limit=source_limit,
                    benchmark_ts_code=benchmark,
                    message_day_max_pct=message_day_max_pct,
                    strong_return_pct=strong_return_pct,
                    limit_like_pct=limit_like_pct,
                ).model_dump()
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/source-radar/validation", response_model=SourceRadarValidationResponse)
def source_radar_validation(
    window_days: int = Query(default=5, ge=1, le=30),
    limit: int = Query(default=12, ge=1, le=50),
    config: RadarConfig = Depends(get_config),
) -> SourceRadarValidationResponse:
    return cached_model(
        config.database_path,
        key=cache_key("strategy.source_radar.validation.v1", {"window_days": window_days, "limit": limit}),
        dependency_key=source_radar_dependency_key(config),
        model_type=SourceRadarValidationResponse,
        compute=lambda: SourceRadarValidationResponse(
            **summarize_source_signal_validation(config, window_days=window_days, limit=limit).model_dump()
        ),
    )


@router.get("/source-radar", response_model=SourceRadarSnapshotResponse)
def strategy_source_radar(
    limit: int = Query(default=20, ge=1, le=100),
    as_of_time: datetime | None = Query(default=None),
    config: RadarConfig = Depends(get_config),
) -> SourceRadarSnapshotResponse:
    return cached_model(
        config.database_path,
        key=cache_key(
            "strategy.source_radar.v2",
            {"limit": limit, "as_of_time": as_of_time.isoformat() if as_of_time else None},
        ),
        dependency_key=source_radar_dependency_key(config),
        model_type=SourceRadarSnapshotResponse,
        compute=lambda: _source_radar_snapshot(config, limit=limit, as_of_time=as_of_time),
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


def _source_radar_snapshot(
    config: RadarConfig,
    *,
    limit: int,
    as_of_time: datetime | None,
) -> SourceRadarSnapshotResponse:
    with connect(config.database_path) as conn:
        migrate_message_db(conn)
        result = list_latest_source_signal_snapshots(conn, as_of_time=as_of_time, limit=limit)
    return SourceRadarSnapshotResponse(**result.model_dump())
