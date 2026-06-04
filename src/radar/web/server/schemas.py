from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import MessageSource, RawMessage
from radar.core.runs import RunRecord

SourceKey = Literal["personal_message", "group_message"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: str
    market_database: str


class MessagePageResponse(BaseModel):
    items: list[RawMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None


class MessageGroupItem(BaseModel):
    group_name: str
    message_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class MessageGroupListResponse(BaseModel):
    items: list[MessageGroupItem]


class RunListResponse(BaseModel):
    items: list[RunRecord]


class IngestWechatRequest(BaseModel):
    source: Literal["all", "personal_message", "group_message"] = "all"
    start_time: datetime
    end_time: datetime
    force: bool = False
    chunk_hours: int = Field(default=1, ge=1, le=24)
    concurrency: int = Field(default=4, ge=1, le=16)


class IngestWechatItem(BaseModel):
    source_key: SourceKey
    source: MessageSource
    chunk_count: int
    skipped_count: int
    raw_count: int
    filtered_count: int
    stored_count: int
    run_id: str | None


class IngestWechatResponse(BaseModel):
    items: list[IngestWechatItem]
