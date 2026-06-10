from __future__ import annotations

from fastapi import APIRouter, Depends

from radar.core.config import RadarConfig
from radar.web.server.aggregate_jobs import submit_market_anchor_update_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    DerivedJobResponse,
    MarketAnchorUpdateRequest,
)

router = APIRouter(prefix="/api", tags=["aggregate"])


@router.post("/market/anchors/jobs", response_model=DerivedJobResponse)
def start_market_anchor_update_job(
    request: MarketAnchorUpdateRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_market_anchor_update_job(config, request)])
