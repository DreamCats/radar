from __future__ import annotations

from fastapi import APIRouter, Depends

from radar.core.config import RadarConfig
from radar.web.server.deps import get_config
from radar.web.server.market_stock_jobs import submit_market_stock_refresh_job
from radar.web.server.schemas import DerivedJobResponse, MarketStockRefreshRequest, ThsConceptRefreshRequest
from radar.web.server.ths_concept_jobs import submit_ths_concept_refresh_job

router = APIRouter(prefix="/api/market", tags=["market"])


@router.post("/stocks/refresh/jobs", response_model=DerivedJobResponse)
def start_market_stock_refresh_job(
    request: MarketStockRefreshRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_market_stock_refresh_job(config, request)])


@router.post("/ths-concepts/refresh/jobs", response_model=DerivedJobResponse)
def start_ths_concept_refresh_job(
    request: ThsConceptRefreshRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_ths_concept_refresh_job(config, request)])
