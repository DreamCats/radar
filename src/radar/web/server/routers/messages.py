from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from radar.core.config import RadarConfig
from radar.core.messages import (
    ConversationFilters,
    CatalystFeedFilters,
    CatalystFeedPage,
    CatalystTermLibrary,
    MessageFilters,
    list_conversations,
    list_catalyst_feed,
    list_message_groups,
    list_messages,
    get_message_overview,
    load_catalyst_terms,
    reset_catalyst_terms,
    save_catalyst_terms,
)
from radar.core.models import MessageSource
from radar.core.storage import connect_readonly
from radar.core.usecases.catalyst_stocks import load_catalyst_stock_detector
from radar.web.server.deps import get_config
from radar.web.server.read_through import request_cache_key, request_operation
from radar.web.server.schemas import (
    ConversationPageResponse,
    MessageGroupListResponse,
    MessageOverviewResponse,
    MessagePageResponse,
)

T = TypeVar("T")

SOURCE_ALIASES: dict[str, MessageSource] = {
    "personal_message": "个人消息",
    "group_message": "个人群",
    "个人消息": "个人消息",
    "个人群": "个人群",
}

router = APIRouter(prefix="/api", tags=["messages"])


@router.get("/messages", response_model=MessagePageResponse)
def messages(
    request: Request,
    source: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
    sender: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    cursor_time: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> MessagePageResponse:
    if bool(cursor_time) != bool(cursor_id):
        raise HTTPException(status_code=400, detail="cursor_time 和 cursor_id 必须一起传")

    source_value = _source_value(source)
    filters = MessageFilters(
        source=source_value,
        group_name=group_name,
        sender=sender,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        cursor_time=cursor_time,
        cursor_id=cursor_id,
        limit=limit,
    )

    def compute() -> MessagePageResponse:
        conn = connect_readonly(config.database_path)
        try:
            page = list_messages(conn, filters)
        finally:
            conn.close()
        return MessagePageResponse(**page.model_dump())

    return _cached_read(request, config, group="normal", ttl_seconds=10.0, compute=compute)


@router.get("/messages/overview", response_model=MessageOverviewResponse)
def messages_overview(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
    top_limit: int = Query(default=8, ge=3, le=20),
    config: RadarConfig = Depends(get_config),
) -> MessageOverviewResponse:
    def compute() -> MessageOverviewResponse:
        conn = connect_readonly(config.database_path)
        try:
            overview = get_message_overview(conn, days=days, top_limit=top_limit)
        finally:
            conn.close()
        return MessageOverviewResponse(**overview.model_dump())

    return _cached_read(request, config, group="normal", ttl_seconds=10.0, compute=compute)


@router.get("/conversations", response_model=ConversationPageResponse)
def conversations(
    request: Request,
    source: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    cursor_time: datetime | None = Query(default=None),
    cursor_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> ConversationPageResponse:
    if bool(cursor_time) != bool(cursor_key):
        raise HTTPException(status_code=400, detail="cursor_time 和 cursor_key 必须一起传")

    filters = ConversationFilters(
        source=_source_value(source),
        group_name=group_name,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        cursor_time=cursor_time,
        cursor_key=cursor_key,
        limit=limit,
    )

    def compute() -> ConversationPageResponse:
        conn = connect_readonly(config.database_path)
        try:
            page = list_conversations(conn, filters)
        finally:
            conn.close()
        return ConversationPageResponse(**page.model_dump())

    return _cached_read(request, config, group="normal", ttl_seconds=10.0, compute=compute)


@router.get("/message-groups", response_model=MessageGroupListResponse)
def message_groups(
    request: Request,
    source: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    config: RadarConfig = Depends(get_config),
) -> MessageGroupListResponse:
    source_value = _source_value(source)

    def compute() -> MessageGroupListResponse:
        conn = connect_readonly(config.database_path)
        try:
            groups = list_message_groups(conn, source=source_value, keyword=keyword, limit=limit)
        finally:
            conn.close()
        return MessageGroupListResponse(items=[group.model_dump() for group in groups])

    return _cached_read(request, config, group="normal", ttl_seconds=10.0, compute=compute)


@router.get("/catalyst/terms", response_model=CatalystTermLibrary)
def catalyst_terms(config: RadarConfig = Depends(get_config)) -> CatalystTermLibrary:
    return load_catalyst_terms(config)


@router.put("/catalyst/terms", response_model=CatalystTermLibrary)
def update_catalyst_terms(
    request: Request,
    library: CatalystTermLibrary,
    config: RadarConfig = Depends(get_config),
) -> CatalystTermLibrary:
    result = save_catalyst_terms(config, library)
    request.app.state.read_coordinator.clear()
    return result


@router.delete("/catalyst/terms", response_model=CatalystTermLibrary)
def delete_catalyst_terms(
    request: Request,
    config: RadarConfig = Depends(get_config),
) -> CatalystTermLibrary:
    result = reset_catalyst_terms(config)
    request.app.state.read_coordinator.clear()
    return result


@router.get("/catalyst/feed", response_model=CatalystFeedPage)
def catalyst_feed(
    request: Request,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    source: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
    category_ids: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    term_category_id: str | None = Query(default=None),
    term: str | None = Query(default=None),
    dedupe: bool = Query(default=True),
    cursor_time: datetime | None = Query(default=None),
    cursor_key: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> CatalystFeedPage:
    if bool(cursor_time) != bool(cursor_key):
        raise HTTPException(status_code=400, detail="cursor_time 和 cursor_key 必须一起传")
    if bool(term_category_id) != bool(term):
        raise HTTPException(status_code=400, detail="term_category_id 和 term 必须一起传")

    filters = CatalystFeedFilters(
        source=_source_value(source),
        group_name=group_name,
        start_time=start_time,
        end_time=end_time,
        category_ids=_split_csv(category_ids),
        keyword=keyword,
        term_category_id=term_category_id,
        term=term,
        dedupe=dedupe,
        cursor_time=cursor_time,
        cursor_key=cursor_key,
        limit=limit,
    )

    def compute() -> CatalystFeedPage:
        conn = connect_readonly(config.database_path)
        try:
            return list_catalyst_feed(
                conn,
                load_catalyst_terms(config),
                filters,
                stock_detector=load_catalyst_stock_detector(config),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    return _cached_read(request, config, group="heavy", ttl_seconds=15.0, compute=compute)


def _cached_read(
    request: Request,
    config: RadarConfig,
    *,
    group: str,
    ttl_seconds: float,
    compute: Callable[[], T],
) -> T:
    scope = f"{config.database_path}:{config.market_database_path}:{config.config_dir}"
    return request.app.state.read_coordinator.get_or_compute(
        key=request_cache_key(request, scope=scope),
        operation=request_operation(request),
        group=group,
        ttl_seconds=ttl_seconds,
        compute=compute,
    )


def _source_value(source: str | None) -> MessageSource | None:
    if not source:
        return None
    if source not in SOURCE_ALIASES:
        raise HTTPException(status_code=400, detail="source 必须是个人消息或个人群")
    return SOURCE_ALIASES[source]


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
