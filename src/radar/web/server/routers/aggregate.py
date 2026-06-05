from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.store import connect, init_db
from radar.core.usecases.aggregation.storage import list_refine_results
from radar.web.server.aggregate_jobs import submit_aggregate_refine_job, submit_anchor_messages_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    AggregateRefineRequest,
    AggregateRefineResultListResponse,
    AnchorMessagesRequest,
    DerivedJobResponse,
)

router = APIRouter(prefix="/api", tags=["aggregate"])


@router.post("/anchor/messages/jobs", response_model=DerivedJobResponse)
def start_anchor_messages_job(
    request: AnchorMessagesRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    _validate_window(request.start_time, request.end_time)
    return DerivedJobResponse(items=[submit_anchor_messages_job(config, request)])


@router.post("/aggregate/refine/jobs", response_model=DerivedJobResponse)
def start_aggregate_refine_job(
    request: AggregateRefineRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    _validate_window(request.start_time, request.end_time)
    if request.provider_name and request.provider_names:
        raise HTTPException(status_code=400, detail="provider_name 和 provider_names 只能二选一")
    return DerivedJobResponse(items=[submit_aggregate_refine_job(config, request)])


@router.get("/aggregate/refine/results", response_model=AggregateRefineResultListResponse)
def aggregate_refine_results(
    limit: int = Query(default=5, ge=1, le=20),
    config: RadarConfig = Depends(get_config),
) -> AggregateRefineResultListResponse:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        return AggregateRefineResultListResponse(items=list_refine_results(conn, limit=limit))
    finally:
        conn.close()


def _validate_window(start_time, end_time) -> None:
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
