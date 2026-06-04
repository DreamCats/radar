from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import ClassificationRetryMode, MessageSource, RawMessage
from radar.core.runs import RunRecord

SourceKey = Literal["personal_message", "group_message"]
JobSourceKey = Literal["all", "personal_message", "group_message"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: str
    market_database: str


class MessagePageResponse(BaseModel):
    items: list[RawMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None


class ConversationItem(BaseModel):
    key: str
    title: str
    source: MessageSource
    latest_sender: str
    latest_time: datetime
    latest_content: str
    latest_message_id: str


class ConversationPageResponse(BaseModel):
    items: list[ConversationItem]
    next_cursor_time: datetime | None = None
    next_cursor_key: str | None = None


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


class IngestWechatJobItem(BaseModel):
    source_key: SourceKey
    source: MessageSource
    run_id: str
    reused_existing: bool = False
    status: Literal["running"]


class IngestWechatJobResponse(BaseModel):
    items: list[IngestWechatJobItem]


class ClassifyMessagesRequest(BaseModel):
    source: JobSourceKey = "all"
    start_time: datetime
    end_time: datetime
    force: bool = False
    chunk_hours: int = Field(default=1, ge=1, le=24)
    limit: int = Field(default=500, ge=1, le=5000)
    batch_size: int = Field(default=16, ge=1, le=64)
    max_concurrency: int = Field(default=10, ge=1, le=32)
    provider_name: str | None = None
    provider_names: list[str] | None = None
    retry: ClassificationRetryMode | None = None
    low_confidence_threshold: float = Field(default=0.65, ge=0, le=1)


class ClassifyMessagesJobItem(BaseModel):
    source_key: JobSourceKey
    source: str
    run_id: str
    reused_existing: bool = False
    status: Literal["running"]


class ClassifyMessagesJobResponse(BaseModel):
    items: list[ClassifyMessagesJobItem]
