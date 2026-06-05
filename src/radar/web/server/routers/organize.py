from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.models import MessageCategory, MessageSource
from radar.core.organize import (
    ORGANIZE_DISPLAY_CONFIDENCE_THRESHOLD,
    OrganizeEvidenceFilters,
    OrganizeClassificationFilters,
    list_classification_clusters,
    list_classification_evidence,
)
from radar.core.organize_aggregates import (
    OrganizeAggregateEvidenceFilters,
    OrganizeAggregateFilters,
    list_aggregate_evidence,
    list_aggregate_themes,
)
from radar.core.store import connect, init_db
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    OrganizeAggregateEvidencePageResponse,
    OrganizeAggregateResponse,
    OrganizeClassificationResponse,
    OrganizeEvidencePageResponse,
)

SOURCE_ALIASES: dict[str, MessageSource] = {
    "personal_message": "个人消息",
    "group_message": "个人群",
    "个人消息": "个人消息",
    "个人群": "个人群",
}

CATEGORIES: set[MessageCategory] = {
    "research",
    "recommendation",
    "event",
    "industry",
    "chat",
}

router = APIRouter(prefix="/api/organize", tags=["organize"])


@router.get("/classifications", response_model=OrganizeClassificationResponse)
def classification_clusters(
    source: str | None = Query(default=None),
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    evidence_limit: int = Query(default=30, ge=0, le=50),
    low_confidence_threshold: float = Query(default=ORGANIZE_DISPLAY_CONFIDENCE_THRESHOLD, ge=0, le=1),
    config: RadarConfig = Depends(get_config),
) -> OrganizeClassificationResponse:
    filters = OrganizeClassificationFilters(
        source=_source_value(source),
        category=_category_value(category),
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        evidence_limit=evidence_limit,
        low_confidence_threshold=low_confidence_threshold,
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_classification_clusters(conn, filters)
    finally:
        conn.close()
    return OrganizeClassificationResponse(**page.model_dump())


@router.get("/classifications/evidence", response_model=OrganizeEvidencePageResponse)
def classification_evidence(
    category: str = Query(),
    source: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    cursor_time: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=50),
    low_confidence_threshold: float = Query(default=ORGANIZE_DISPLAY_CONFIDENCE_THRESHOLD, ge=0, le=1),
    config: RadarConfig = Depends(get_config),
) -> OrganizeEvidencePageResponse:
    if bool(cursor_time) != bool(cursor_id):
        raise HTTPException(status_code=400, detail="cursor_time 和 cursor_id 必须一起传")

    filters = OrganizeEvidenceFilters(
        source=_source_value(source),
        category=_category_value(category),
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        cursor_time=cursor_time,
        cursor_id=cursor_id,
        limit=limit,
        low_confidence_threshold=low_confidence_threshold,
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_classification_evidence(conn, filters)
    finally:
        conn.close()
    return OrganizeEvidencePageResponse(**page.model_dump())


@router.get("/aggregates", response_model=OrganizeAggregateResponse)
def aggregate_themes(
    source: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    evidence_limit: int = Query(default=30, ge=0, le=100),
    config: RadarConfig = Depends(get_config),
) -> OrganizeAggregateResponse:
    filters = OrganizeAggregateFilters(
        source=_source_value(source),
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        evidence_limit=evidence_limit,
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_aggregate_themes(conn, filters)
    finally:
        conn.close()
    return OrganizeAggregateResponse(**page.model_dump())


@router.get("/aggregates/evidence", response_model=OrganizeAggregateEvidencePageResponse)
def aggregate_evidence(
    run_id: str = Query(),
    theme_index: int = Query(ge=0),
    source: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    cursor_time: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=50),
    config: RadarConfig = Depends(get_config),
) -> OrganizeAggregateEvidencePageResponse:
    if bool(cursor_time) != bool(cursor_id):
        raise HTTPException(status_code=400, detail="cursor_time 和 cursor_id 必须一起传")

    filters = OrganizeAggregateEvidenceFilters(
        run_id=run_id,
        theme_index=theme_index,
        source=_source_value(source),
        keyword=keyword,
        cursor_time=cursor_time,
        cursor_id=cursor_id,
        limit=limit,
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_aggregate_evidence(conn, filters)
    finally:
        conn.close()
    return OrganizeAggregateEvidencePageResponse(**page.model_dump())


def _source_value(source: str | None) -> MessageSource | None:
    if not source:
        return None
    if source not in SOURCE_ALIASES:
        raise HTTPException(status_code=400, detail="source 必须是个人消息或个人群")
    return SOURCE_ALIASES[source]


def _category_value(category: str | None) -> MessageCategory | None:
    if not category:
        return None
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="category 不合法")
    return category
