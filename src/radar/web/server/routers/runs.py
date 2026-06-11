from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.storage import RunRecord, RunStatus, cancel_run, list_runs
from radar.web.server.backtest_jobs import mark_stale_backtest_runs
from radar.web.server.classify_jobs import mark_stale_classify_runs
from radar.web.server.deps import get_config
from radar.web.server.ingest_jobs import mark_stale_ingest_runs
from radar.web.server.market_anchor_jobs import mark_stale_market_anchor_runs
from radar.web.server.strategy_jobs import mark_stale_stock_evidence_chain_runs
from radar.web.server.schemas import RunListResponse

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs", response_model=RunListResponse)
def runs(
    kind: str | None = Query(default=None),
    kinds: str | None = Query(default=None),
    status: RunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> RunListResponse:
    mark_stale_ingest_runs(config)
    mark_stale_classify_runs(config)
    mark_stale_market_anchor_runs(config)
    mark_stale_backtest_runs(config)
    mark_stale_stock_evidence_chain_runs(config)
    kind_list = [item.strip() for item in kinds.split(",") if item.strip()] if kinds else None
    return RunListResponse(items=list_runs(config.database_path, kind=kind, kinds=kind_list, status=status, limit=limit))


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
def cancel(run_id: str, config: RadarConfig = Depends(get_config)) -> RunRecord:
    run = cancel_run(config.database_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return run
