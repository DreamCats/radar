from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from radar.core.config import RadarConfig
from radar.web.server.classify_jobs import submit_classify_messages_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import ClassifyMessagesJobResponse, ClassifyMessagesRequest

router = APIRouter(prefix="/api/classify", tags=["classify"])


@router.post("/messages/jobs", response_model=ClassifyMessagesJobResponse)
def start_classify_messages_job(
    request: ClassifyMessagesRequest,
    config: RadarConfig = Depends(get_config),
) -> ClassifyMessagesJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    if request.provider_name and request.provider_names:
        raise HTTPException(status_code=400, detail="provider_name 和 provider_names 只能二选一")

    return ClassifyMessagesJobResponse(items=submit_classify_messages_job(config, request))
