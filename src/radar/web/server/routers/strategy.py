from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.usecases.strategy import build_strategy_dashboard
from radar.web.server.deps import get_config
from radar.web.server.schemas import StrategyDashboardResponse

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/opportunities", response_model=StrategyDashboardResponse)
def strategy_opportunities(
    days: int = Query(default=30, ge=7, le=180),
    recent_days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=10, ge=1, le=50),
    config: RadarConfig = Depends(get_config),
) -> StrategyDashboardResponse:
    try:
        result = build_strategy_dashboard(config, days=days, recent_days=recent_days, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyDashboardResponse(**result.model_dump())
