from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from radar.core.dashboard import DashboardSummaryPayload
from radar.core.models import ClassificationRetryMode, MessageSource, RawMessage
from radar.core.organize import (
    OrganizeClassificationCluster,
    OrganizeClassificationSummary,
    OrganizeEvidenceMessage,
)
from radar.core.scheduler import ScheduleRecord, ScheduleTickRecord
from radar.core.storage import RunRecord
from radar.core.usecases.analyst_mentions import (
    DEFAULT_BENCHMARK_TS_CODE,
    AnalystMentionEvidenceResult,
    AnalystMentionMessageEvidenceResult,
    AnalystMentionSummaryResult,
)
from radar.core.usecases.stock_evidence_chain import (
    LifecycleDigestPreview,
    StockEvidenceChainDashboard,
    StockEvidenceChainSnapshotList,
    StockEvidenceFinancials,
    StockEvidenceStockChart,
)

SourceKey = Literal["personal_message", "group_message"]
JobSourceKey = Literal["all", "personal_message", "group_message"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: str
    market_database: str


class AuthStatusResponse(BaseModel):
    auth_required: bool
    authenticated: bool
    username: str | None = None


class IndustryChainIndexItem(BaseModel):
    chain_id: str
    title: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    status: str
    sort_order: int = 0
    content_path: str
    data_path: str
    updated_at: str
    entry_tags: list[str] = Field(default_factory=list)
    audience_level: str | None = None
    evidence_level: str | None = None
    summary: str


class IndustryChainListResponse(BaseModel):
    version: int
    updated_at: str
    items: list[IndustryChainIndexItem]


class IndustryChainDetailResponse(BaseModel):
    item: IndustryChainIndexItem
    data: dict[str, Any]
    content_markdown: str


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


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


class ScheduleListResponse(BaseModel):
    items: list[ScheduleRecord]


class ScheduleTickListResponse(BaseModel):
    items: list[ScheduleTickRecord]


class ScheduleRunNowResponse(BaseModel):
    item: ScheduleTickRecord


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


class AnalystBacktestRequest(BaseModel):
    as_of: date
    lookback_days: int = Field(default=40, ge=1, le=120)
    start_time: datetime | None = None
    end_time: datetime | None = None
    windows: list[int] = Field(default_factory=lambda: [1, 3, 5])
    source: JobSourceKey = "all"
    cooldown_trade_days: int = Field(default=5, ge=0, le=30)
    min_classification_confidence: float = Field(default=0.7, ge=0, le=1)
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    remote_price_fetch: bool = True


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


class LifecycleDigestJobRequest(BaseModel):
    limit: int = Field(default=120, ge=1, le=500)
    force: bool = False
    llm_workers: int = Field(default=16, ge=1, le=64)
    provider_names: list[str] | None = None
    model: str | None = None


class DerivedJobItem(BaseModel):
    job_type: Literal[
        "anchor",
        "analyst_backtest",
        "stock_evidence_chain",
        "lifecycle_digest",
    ]
    run_id: str
    reused_existing: bool = False
    status: Literal["running"]


class DerivedJobResponse(BaseModel):
    items: list[DerivedJobItem]


class AnalystMentionSummaryResponse(AnalystMentionSummaryResult):
    pass


class AnalystMentionEvidenceResponse(AnalystMentionEvidenceResult):
    pass


class AnalystMentionMessageEvidenceResponse(AnalystMentionMessageEvidenceResult):
    pass


class StockEvidenceChainDashboardResponse(StockEvidenceChainDashboard):
    pass


class StockEvidenceChainSnapshotListResponse(StockEvidenceChainSnapshotList):
    pass


class StockEvidenceStockChartResponse(StockEvidenceStockChart):
    pass


class StockEvidenceFinancialsResponse(StockEvidenceFinancials):
    pass


class LifecycleDigestPreviewResponse(LifecycleDigestPreview):
    pass


class ChatTurnRequest(BaseModel):
    session_id: str | None = None
    title: str | None = None
    content: str = Field(min_length=1, max_length=8000)
    provider_name: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatContinueRequest(BaseModel):
    provider_name: str | None = None


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
    can_continue: bool = False


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


class ChatRunResponse(BaseModel):
    run_id: str
    session_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    created_at: str
    updated_at: str
    last_seq: int = 0
    cancel_requested: bool = False
    error: str | None = None


class ChatRunStartResponse(BaseModel):
    run: ChatRunResponse


class ChatActiveRunResponse(BaseModel):
    run: ChatRunResponse | None = None


class OrganizeClassificationResponse(BaseModel):
    summary: OrganizeClassificationSummary
    clusters: list[OrganizeClassificationCluster]


class OrganizeEvidencePageResponse(BaseModel):
    items: list[OrganizeEvidenceMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None
