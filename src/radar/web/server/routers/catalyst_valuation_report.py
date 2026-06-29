from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from radar.core.config import RadarConfig
from radar.web.server.catalyst_valuation_report_jobs import submit_catalyst_valuation_report_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import CatalystValuationReportJobRequest, DerivedJobResponse

router = APIRouter(prefix="/api", tags=["catalyst-valuation-report"])


@router.post("/catalyst-valuation-report/jobs", response_model=DerivedJobResponse)
def start_catalyst_valuation_report_job(
    request: CatalystValuationReportJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    return DerivedJobResponse(items=[submit_catalyst_valuation_report_job(config, request)])
