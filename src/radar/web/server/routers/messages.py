from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.query import MessageFilters, list_message_groups, list_messages
from radar.core.store import connect, init_db
from radar.web.server.deps import get_config
from radar.web.server.schemas import MessageGroupListResponse, MessagePageResponse

SOURCE_ALIASES: dict[str, MessageSource] = {
    "personal_message": "个人消息",
    "group_message": "个人群",
    "个人消息": "个人消息",
    "个人群": "个人群",
}

router = APIRouter(prefix="/api", tags=["messages"])


@router.get("/messages", response_model=MessagePageResponse)
def messages(
    source: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
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
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        cursor_time=cursor_time,
        cursor_id=cursor_id,
        limit=limit,
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_messages(conn, filters)
    finally:
        conn.close()
    return MessagePageResponse(**page.model_dump())


@router.get("/message-groups", response_model=MessageGroupListResponse)
def message_groups(
    source: str | None = Query(default="group_message"),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    config: RadarConfig = Depends(get_config),
) -> MessageGroupListResponse:
    source_value = _source_value(source)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        groups = list_message_groups(conn, source=source_value, keyword=keyword, limit=limit)
    finally:
        conn.close()
    return MessageGroupListResponse(items=[group.model_dump() for group in groups])


def _source_value(source: str | None) -> MessageSource | None:
    if not source:
        return None
    if source not in SOURCE_ALIASES:
        raise HTTPException(status_code=400, detail="source 必须是个人消息或个人群")
    return SOURCE_ALIASES[source]
