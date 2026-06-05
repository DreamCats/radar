from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import ClassificationRetryMode, MessageCategory, MessageSource, RawMessage
from radar.core.organize import OrganizeClassificationCluster, OrganizeClassificationSummary, OrganizeEvidenceMessage
from radar.core.organize_aggregates import (
    OrganizeAggregateEvidencePage,
    OrganizeAggregatePage,
)
from radar.core.runs import RunRecord
from radar.core.usecases.aggregation import RefineAggregateTopicsResult

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


class MessageOverviewSummaryResponse(BaseModel):
    total_count: int
    group_message_count: int
    personal_message_count: int
    group_count: int
    sender_count: int
    first_message_time: datetime | None = None
    latest_message_time: datetime | None = None


class MessageOverviewBucketResponse(BaseModel):
    date: str
    total_count: int
    group_message_count: int
    personal_message_count: int


class MessageOverviewSourceResponse(BaseModel):
    source: MessageSource
    count: int


class MessageOverviewGroupResponse(BaseModel):
    group_name: str
    count: int
    last_message_time: datetime


class MessageOverviewHourResponse(BaseModel):
    hour: int
    count: int


class MessageAnchorHeatResponse(BaseModel):
    name: str
    anchor_type: Literal["stock", "concept", "industry", "theme"]
    mention_count: int
    message_count: int
    high_value_count: int
    average_confidence: float
    latest_message_time: datetime


class MessageOverviewResponse(BaseModel):
    summary: MessageOverviewSummaryResponse
    date_buckets: list[MessageOverviewBucketResponse]
    source_breakdown: list[MessageOverviewSourceResponse]
    top_groups: list[MessageOverviewGroupResponse]
    hourly_buckets: list[MessageOverviewHourResponse]
    anchor_heat: list[MessageAnchorHeatResponse]


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


class AnchorMessagesRequest(BaseModel):
    trade_date: str
    source: JobSourceKey = "all"
    start_time: datetime
    end_time: datetime
    force: bool = False
    chunk_hours: int = Field(default=1, ge=1, le=24)
    limit: int = Field(default=500, ge=1, le=5000)
    categories: list[MessageCategory] = Field(default_factory=lambda: ["research", "recommendation", "industry"])
    min_classification_confidence: float = Field(default=0.7, ge=0, le=1)
    max_anchors: int = Field(default=7, ge=1, le=20)


class AggregateRefineRequest(BaseModel):
    trade_date: str
    source: JobSourceKey = "all"
    start_time: datetime
    end_time: datetime
    force: bool = False
    categories: list[MessageCategory] = Field(default_factory=lambda: ["research", "recommendation", "industry"])
    min_classification_confidence: float = Field(default=0.7, ge=0, le=1)
    min_messages: int = Field(default=2, ge=1, le=100)
    candidate_limit: int = Field(default=50, ge=1, le=100)
    evidence_limit: int = Field(default=3, ge=0, le=10)
    batch_size: int = Field(default=5, ge=1, le=30)
    max_concurrency: int = Field(default=10, ge=1, le=16)
    provider_name: str | None = None
    provider_names: list[str] | None = None


class DerivedJobItem(BaseModel):
    job_type: Literal["anchor", "aggregate_refine"]
    run_id: str
    reused_existing: bool = False
    status: Literal["running"]


class DerivedJobResponse(BaseModel):
    items: list[DerivedJobItem]


class AggregateRefineResultListResponse(BaseModel):
    items: list[RefineAggregateTopicsResult]


class OrganizeClassificationResponse(BaseModel):
    summary: OrganizeClassificationSummary
    clusters: list[OrganizeClassificationCluster]


class OrganizeEvidencePageResponse(BaseModel):
    items: list[OrganizeEvidenceMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None


class OrganizeAggregateResponse(OrganizeAggregatePage):
    pass


class OrganizeAggregateEvidencePageResponse(OrganizeAggregateEvidencePage):
    pass
