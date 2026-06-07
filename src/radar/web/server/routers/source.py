from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from radar.core.config import RadarConfig
from radar.web.server.deps import get_config
from radar.web.server.schemas import DerivedJobResponse, SourceRadarJobRequest
from radar.web.server.source_jobs import submit_source_radar_job

router = APIRouter(prefix="/api/source", tags=["source"])


@router.post("/radar/jobs", response_model=DerivedJobResponse)
def start_source_radar_job(
    request: SourceRadarJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    if request.provider_name and request.provider_names:
        raise HTTPException(status_code=400, detail="provider_name 和 provider_names 只能二选一")
    return DerivedJobResponse(items=[submit_source_radar_job(config, request)])
