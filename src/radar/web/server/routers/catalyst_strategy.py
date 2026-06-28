from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from radar.core.config import RadarConfig
from radar.web.server.catalyst_strategy_jobs import submit_catalyst_strategy_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import CatalystStrategyJobRequest, DerivedJobResponse

router = APIRouter(prefix="/api", tags=["catalyst-strategy"])


@router.post("/catalyst-strategy/jobs", response_model=DerivedJobResponse)
def start_catalyst_strategy_job(
    request: CatalystStrategyJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    return DerivedJobResponse(items=[submit_catalyst_strategy_job(config, request)])
