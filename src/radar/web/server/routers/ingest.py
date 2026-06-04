from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from radar.core.config import RadarConfig
from radar.core.usecases import ingest_wechat_range
from radar.web.server.deps import get_config
from radar.web.server.ingest_jobs import submit_wechat_ingest_jobs
from radar.web.server.schemas import (
    IngestWechatItem,
    IngestWechatJobResponse,
    IngestWechatRequest,
    IngestWechatResponse,
)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/wechat", response_model=IngestWechatResponse)
def ingest_wechat(
    request: IngestWechatRequest,
    config: RadarConfig = Depends(get_config),
) -> IngestWechatResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    source_keys = list(config.wechat.sources) if request.source == "all" else [request.source]
    items: list[IngestWechatItem] = []
    for source_key in source_keys:
        result = ingest_wechat_range(
            config,
            source_key=source_key,
            start_time=request.start_time,
            end_time=request.end_time,
            force=request.force,
            chunk_hours=request.chunk_hours,
            concurrency=request.concurrency,
        )
        items.append(
            IngestWechatItem(
                source_key=source_key,
                source=result.source,
                chunk_count=result.chunk_count,
                skipped_count=result.skipped_count,
                raw_count=result.raw_count,
                filtered_count=result.filtered_count,
                stored_count=result.stored_count,
                run_id=result.run_id,
            )
        )
    return IngestWechatResponse(items=items)


@router.post("/wechat/jobs", response_model=IngestWechatJobResponse)
def start_ingest_wechat_job(
    request: IngestWechatRequest,
    config: RadarConfig = Depends(get_config),
) -> IngestWechatJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    return IngestWechatJobResponse(items=submit_wechat_ingest_jobs(config, request))
