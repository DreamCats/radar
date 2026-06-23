from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.usecases.analyst_mentions import (
    DEFAULT_ANALYST_MENTION_WINDOWS,
    list_analyst_stock_mention_evidence,
    list_analyst_stock_mention_message_evidence,
    summarize_analyst_stock_mentions,
)
from radar.web.server.backtest_jobs import submit_analyst_backtest_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    AnalystBacktestRequest,
    AnalystMentionEvidenceResponse,
    AnalystMentionMessageEvidenceResponse,
    AnalystMentionSummaryResponse,
    DerivedJobResponse,
    JobSourceKey,
)

router = APIRouter(prefix="/api", tags=["backtest"])

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}


@router.post("/analyst/backtest/jobs", response_model=DerivedJobResponse)
def start_analyst_backtest_job(
    request: AnalystBacktestRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    return DerivedJobResponse(items=[submit_analyst_backtest_job(config, request)])


@router.get("/analyst/backtest/summary", response_model=AnalystMentionSummaryResponse)
def analyst_backtest_summary(
    start_time: datetime,
    end_time: datetime,
    source: JobSourceKey = Query(default="all"),
    window: list[int] | None = Query(default=None),
    min_count: int = Query(default=3, ge=1, le=1000),
    limit: int = Query(default=20, ge=1, le=200),
    include_broad_list: bool = Query(default=False),
    config: RadarConfig = Depends(get_config),
) -> AnalystMentionSummaryResponse:
    try:
        result = summarize_analyst_stock_mentions(
            config,
            start_time=start_time,
            end_time=end_time,
            windows=window or list(DEFAULT_ANALYST_MENTION_WINDOWS),
            source=_SOURCE_MAP[source],
            min_count=min_count,
            limit=limit,
            include_broad_list=include_broad_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalystMentionSummaryResponse.model_validate(result.model_dump())


@router.get("/analyst/backtest/evidence", response_model=AnalystMentionEvidenceResponse)
def analyst_backtest_evidence(
    start_time: datetime,
    end_time: datetime,
    window: int = Query(default=5, ge=1, le=30),
    analyst: str | None = Query(default=None),
    ts_code: str | None = Query(default=None),
    source: JobSourceKey = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    include_broad_list: bool = Query(default=False),
    config: RadarConfig = Depends(get_config),
) -> AnalystMentionEvidenceResponse:
    try:
        result = list_analyst_stock_mention_evidence(
            config,
            start_time=start_time,
            end_time=end_time,
            window=window,
            analyst=analyst,
            ts_code=ts_code,
            source=_SOURCE_MAP[source],
            limit=limit,
            include_broad_list=include_broad_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalystMentionEvidenceResponse.model_validate(result.model_dump())


@router.get("/analyst/backtest/message-evidence", response_model=AnalystMentionMessageEvidenceResponse)
def analyst_backtest_message_evidence(
    start_time: datetime,
    end_time: datetime,
    window: int = Query(default=5, ge=1, le=30),
    analyst: str | None = Query(default=None),
    source: JobSourceKey = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    include_broad_list: bool = Query(default=False),
    config: RadarConfig = Depends(get_config),
) -> AnalystMentionMessageEvidenceResponse:
    try:
        result = list_analyst_stock_mention_message_evidence(
            config,
            start_time=start_time,
            end_time=end_time,
            window=window,
            analyst=analyst,
            source=_SOURCE_MAP[source],
            limit=limit,
            include_broad_list=include_broad_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalystMentionMessageEvidenceResponse.model_validate(result.model_dump())
