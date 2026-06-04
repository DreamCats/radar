from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from radar.core.config import RadarConfig
from radar.core.runs import RunStatus, list_runs
from radar.web.server.deps import get_config
from radar.web.server.schemas import RunListResponse

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs", response_model=RunListResponse)
def runs(
    kind: str | None = Query(default=None),
    status: RunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> RunListResponse:
    return RunListResponse(items=list_runs(config.database_path, kind=kind, status=status, limit=limit))

