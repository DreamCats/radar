from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.usecases.recommendation_backtest import (
    DEFAULT_BACKTEST_WINDOWS,
    BacktestGroupBy,
    summarize_recommendation_backtests,
)
from radar.web.server.backtest_jobs import submit_recommendation_backtest_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    DerivedJobResponse,
    JobSourceKey,
    RecommendationBacktestRequest,
    RecommendationBacktestSummaryResponse,
)

router = APIRouter(prefix="/api", tags=["backtest"])

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}


@router.post("/recommendation/backtest/jobs", response_model=DerivedJobResponse)
def start_recommendation_backtest_job(
    request: RecommendationBacktestRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_recommendation_backtest_job(config, request)])


@router.get("/recommendation/backtest/summary", response_model=RecommendationBacktestSummaryResponse)
def recommendation_backtest_summary(
    start_time: datetime,
    end_time: datetime,
    source: JobSourceKey = Query(default="all"),
    group_by: BacktestGroupBy = Query(default="analyst_sector"),
    window: list[int] | None = Query(default=None, ge=1, le=30),
    min_count: int = Query(default=3, ge=1, le=1000),
    limit: int = Query(default=20, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> RecommendationBacktestSummaryResponse:
    try:
        result = summarize_recommendation_backtests(
            config,
            start_time=start_time,
            end_time=end_time,
            group_by=cast(BacktestGroupBy, group_by),
            windows=window or list(DEFAULT_BACKTEST_WINDOWS),
            source=_SOURCE_MAP[source],
            min_count=min_count,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RecommendationBacktestSummaryResponse.model_validate(result.model_dump())
