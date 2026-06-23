from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.scheduler import (
    ensure_default_schedules,
    get_schedule,
    list_schedule_ticks,
    list_schedules,
    scheduler_now,
    set_schedule_enabled,
)
from radar.web.server.deps import get_config
from radar.web.server.scheduler import run_schedule_now
from radar.web.server.schemas import (
    ScheduleListResponse,
    ScheduleRunNowResponse,
    ScheduleTickListResponse,
)

router = APIRouter(prefix="/api", tags=["schedules"])


@router.get("/schedules", response_model=ScheduleListResponse)
def schedules(config: RadarConfig = Depends(get_config)) -> ScheduleListResponse:
    ensure_default_schedules(config.database_path)
    return ScheduleListResponse(items=list_schedules(config.database_path))


@router.post("/schedules/{schedule_id}/enable", response_model=ScheduleListResponse)
def enable_schedule(schedule_id: str, config: RadarConfig = Depends(get_config)) -> ScheduleListResponse:
    updated = set_schedule_enabled(config.database_path, schedule_id, enabled=True, now=scheduler_now())
    if updated is None:
        raise HTTPException(status_code=404, detail="schedule 不存在")
    return ScheduleListResponse(items=list_schedules(config.database_path))


@router.post("/schedules/{schedule_id}/disable", response_model=ScheduleListResponse)
def disable_schedule(schedule_id: str, config: RadarConfig = Depends(get_config)) -> ScheduleListResponse:
    updated = set_schedule_enabled(config.database_path, schedule_id, enabled=False, now=scheduler_now())
    if updated is None:
        raise HTTPException(status_code=404, detail="schedule 不存在")
    return ScheduleListResponse(items=list_schedules(config.database_path))


@router.post("/schedules/{schedule_id}/run-now", response_model=ScheduleRunNowResponse)
def run_now(schedule_id: str, config: RadarConfig = Depends(get_config)) -> ScheduleRunNowResponse:
    schedule = get_schedule(config.database_path, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule 不存在")
    return ScheduleRunNowResponse(item=run_schedule_now(config, schedule, now=scheduler_now()))


@router.get("/schedules/{schedule_id}/ticks", response_model=ScheduleTickListResponse)
def ticks(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> ScheduleTickListResponse:
    if get_schedule(config.database_path, schedule_id) is None:
        raise HTTPException(status_code=404, detail="schedule 不存在")
    return ScheduleTickListResponse(items=list_schedule_ticks(config.database_path, schedule_id=schedule_id, limit=limit))
