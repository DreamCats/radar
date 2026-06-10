from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from radar.core.models import ClassificationRetryMode, MessageCategory, MessageSource, RawMessage
from radar.core.dashboard import DashboardSummaryPayload
from radar.core.organize import OrganizeClassificationCluster, OrganizeClassificationSummary, OrganizeEvidenceMessage
from radar.core.runs import RunRecord
from radar.core.usecases.recommendation_backtest import (
    DEFAULT_BENCHMARK_TS_CODE,
    DEFAULT_BACKTEST_WINDOWS,
    RecommendationBacktestSummaryResult,
)
from radar.core.usecases.stock_evidence_chain import (
    StockEvidenceChainDashboard,
    StockEvidenceStockChart,
)

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


class MessageOverviewResponse(BaseModel):
    summary: MessageOverviewSummaryResponse
    date_buckets: list[MessageOverviewBucketResponse]
    source_breakdown: list[MessageOverviewSourceResponse]
    top_groups: list[MessageOverviewGroupResponse]
    hourly_buckets: list[MessageOverviewHourResponse]


class RunListResponse(BaseModel):
    items: list[RunRecord]


class DashboardSummaryResponse(DashboardSummaryPayload):
    runs: list[RunRecord]


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


class MarketAnchorUpdateRequest(BaseModel):
    trade_date: str
    force: bool = False
    min_anchor_count: int = Field(default=100, ge=1, le=100000)


class RecommendationBacktestRequest(BaseModel):
    as_of: date
    window_days: int = Field(default=30, ge=1, le=365)
    start_time: datetime | None = None
    end_time: datetime | None = None
    windows: list[int] = Field(default_factory=lambda: list(DEFAULT_BACKTEST_WINDOWS))
    source: JobSourceKey = "all"
    min_classification_confidence: float = Field(default=0.7, ge=0, le=1)
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    force: bool = False


class StockEvidenceChainJobRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    evidence_days: int = Field(default=40, ge=7, le=90)
    limit: int = Field(default=120, ge=1, le=500)
    run_llm: bool = True
    llm_workers: int = Field(default=16, ge=1, le=64)
    provider_names: list[str] | None = None
    model: str | None = None
    force_llm: bool = False


class DerivedJobItem(BaseModel):
    job_type: Literal["anchor", "recommendation_backtest", "stock_evidence_chain"]
    run_id: str
    reused_existing: bool = False
    status: Literal["running"]


class DerivedJobResponse(BaseModel):
    items: list[DerivedJobItem]


class RecommendationBacktestSummaryResponse(RecommendationBacktestSummaryResult):
    pass


class StockEvidenceChainDashboardResponse(StockEvidenceChainDashboard):
    pass


class StockEvidenceStockChartResponse(StockEvidenceStockChart):
    pass


class ChatTurnRequest(BaseModel):
    session_id: str | None = None
    title: str | None = None
    content: str = Field(min_length=1, max_length=8000)
    provider_name: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSessionResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    preview: str = ""


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]


class ChatSessionDetailResponse(BaseModel):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ChatModelOptionResponse(BaseModel):
    provider_name: str
    label: str
    protocol: Literal["openai", "anthropic"]
    model: str
    context_window_tokens: int = 256_000
    is_default: bool = False
    thinking_enabled: bool = True


class ChatModelOptionsResponse(BaseModel):
    default_provider_name: str | None = None
    items: list[ChatModelOptionResponse]


class ChatTurnResponse(BaseModel):
    session_id: str
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    tool_messages: list[ChatMessageResponse] = Field(default_factory=list)


class OrganizeClassificationResponse(BaseModel):
    summary: OrganizeClassificationSummary
    clusters: list[OrganizeClassificationCluster]


class OrganizeEvidencePageResponse(BaseModel):
    items: list[OrganizeEvidenceMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None
