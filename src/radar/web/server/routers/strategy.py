from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.usecases.stock_evidence_chain import (
    get_stock_evidence_financials,
    get_stock_evidence_stock_chart,
    latest_stock_evidence_chain,
    list_stock_evidence_chain_snapshots,
    preview_lifecycle_digests,
    stock_evidence_chain,
)
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    DerivedJobResponse,
    LifecycleDigestJobRequest,
    LifecycleDigestPreviewResponse,
    StockEvidenceChainJobRequest,
    StockEvidenceChainDashboardResponse,
    StockEvidenceFinancialsResponse,
    StockEvidenceChainSnapshotListResponse,
    StockEvidenceStockChartResponse,
)
from radar.web.server.strategy_jobs import submit_lifecycle_digest_job, submit_stock_evidence_chain_job

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/evidence-chain/latest", response_model=StockEvidenceChainDashboardResponse)
def stock_evidence_chain_latest(
    limit: int = Query(default=120, ge=1, le=500),
    as_of_time: datetime | None = Query(default=None),
    config: RadarConfig = Depends(get_config),
) -> StockEvidenceChainDashboardResponse:
    result = (
        stock_evidence_chain(config, as_of=as_of_time, limit=limit)
        if as_of_time is not None
        else latest_stock_evidence_chain(config, limit=limit)
    )
    return StockEvidenceChainDashboardResponse(**result.model_dump())


@router.get("/evidence-chain/snapshots", response_model=StockEvidenceChainSnapshotListResponse)
def stock_evidence_chain_snapshots(
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> StockEvidenceChainSnapshotListResponse:
    return StockEvidenceChainSnapshotListResponse(
        **list_stock_evidence_chain_snapshots(config, limit=limit).model_dump()
    )


@router.get("/stocks/{ts_code}/chart", response_model=StockEvidenceStockChartResponse)
def stock_evidence_stock_chart(
    ts_code: str,
    days: int = Query(default=120, ge=1, le=260),
    refresh: bool = Query(default=False),
    config: RadarConfig = Depends(get_config),
) -> StockEvidenceStockChartResponse:
    try:
        result = get_stock_evidence_stock_chart(config, ts_code=ts_code, days=days, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StockEvidenceStockChartResponse(**result.model_dump())


@router.get("/stocks/{ts_code}/financials", response_model=StockEvidenceFinancialsResponse)
def stock_evidence_financials(
    ts_code: str,
    years: int = Query(default=5, ge=1, le=10),
    config: RadarConfig = Depends(get_config),
) -> StockEvidenceFinancialsResponse:
    try:
        result = get_stock_evidence_financials(config, ts_code=ts_code, years=years)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StockEvidenceFinancialsResponse(**result.model_dump())


@router.post("/evidence-chain/jobs", response_model=DerivedJobResponse)
def start_stock_evidence_chain_job(
    request: StockEvidenceChainJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    return DerivedJobResponse(items=[submit_stock_evidence_chain_job(config, request)])


@router.get("/lifecycle-digests/preview", response_model=LifecycleDigestPreviewResponse)
def lifecycle_digest_preview(
    limit: int = Query(default=20, ge=1, le=500),
    force: bool = Query(default=False),
    config: RadarConfig = Depends(get_config),
) -> LifecycleDigestPreviewResponse:
    return LifecycleDigestPreviewResponse(**preview_lifecycle_digests(config, limit=limit, force=force).model_dump())


@router.post("/lifecycle-digests/jobs", response_model=DerivedJobResponse)
def start_lifecycle_digest_job(
    request: LifecycleDigestJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_lifecycle_digest_job(config, request)])
