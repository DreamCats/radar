from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from radar.core.config import RadarConfig
from radar.core.storage import RunRecord, RunStatus, cancel_run, list_runs
from radar.web.server.deps import get_config
from radar.web.server.read_through import request_cache_key, request_operation
from radar.web.server.schemas import RunListResponse

router = APIRouter(prefix="/api", tags=["runs"])
T = TypeVar("T")


@router.get("/runs", response_model=RunListResponse)
def runs(
    request: Request,
    kind: str | None = Query(default=None),
    kinds: str | None = Query(default=None),
    status: RunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> RunListResponse:
    kind_list = [item.strip() for item in kinds.split(",") if item.strip()] if kinds else None

    def compute() -> RunListResponse:
        return RunListResponse(
            items=list_runs(
                config.database_path,
                kind=kind,
                kinds=kind_list,
                status=status,
                limit=limit,
                readonly=True,
            )
        )

    return _cached_read(request, config, ttl_seconds=2.0, compute=compute)


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
def cancel(run_id: str, config: RadarConfig = Depends(get_config)) -> RunRecord:
    run = cancel_run(config.database_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return run


def _cached_read(
    request: Request,
    config: RadarConfig,
    *,
    ttl_seconds: float,
    compute: Callable[[], T],
) -> T:
    scope = f"{config.database_path}:runs"
    return request.app.state.read_coordinator.get_or_compute(
        key=request_cache_key(request, scope=scope),
        operation=request_operation(request),
        group="normal",
        ttl_seconds=ttl_seconds,
        compute=compute,
    )
