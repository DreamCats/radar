from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ANALYST_MENTION_EXTRACTOR_VERSION = "analyst-stock-mention-v1"
DEFAULT_ANALYST_MENTION_WINDOWS: tuple[int, ...] = (1, 3, 5)
DEFAULT_COOLDOWN_TRADE_DAYS = 5
DEFAULT_LOOKBACK_DAYS = 40
DEFAULT_BENCHMARK_TS_CODE = "000300.SH"
DEFAULT_REMOTE_PRICE_FETCH = False
DEFAULT_BROAD_LIST_STOCK_THRESHOLD = 8
QUALITY_FLAG_BROAD_LIST = "broad_list"

MentionWindowStatus = Literal["pending", "succeeded", "missing_price", "failed"]


class AnalystMentionEvent(BaseModel):
    mention_id: str
    message_id: str
    source: str
    sender: str
    analyst_id: str
    analyst_display_name: str
    analyst_alias_key: str
    group_name: str | None = None
    ts_code: str
    stock_name: str
    symbol: str
    message_time: datetime
    event_date: str
    evidence_snippet: str
    content_fingerprint: str
    extractor_version: str
    stock_count_in_message: int = 1
    quality_flags: tuple[str, ...] = ()
    is_effective: bool = True
    dedupe_key: str
    dedupe_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalystMentionBacktestWindow(BaseModel):
    mention_id: str
    window_days: int
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    base_trade_date: str | None = None
    target_trade_date: str | None = None
    base_close: float | None = None
    target_close: float | None = None
    return_rate: float | None = None
    positive: bool | None = None
    benchmark_base_close: float | None = None
    benchmark_target_close: float | None = None
    benchmark_return_rate: float | None = None
    excess_return_rate: float | None = None
    status: MentionWindowStatus
    error_message: str | None = None
    updated_at: datetime


class AnalystMentionRefreshResult(BaseModel):
    run_id: str
    as_of: date
    start_time: datetime
    end_time: datetime
    windows: list[int] = Field(default_factory=list)
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    extractor_version: str = ANALYST_MENTION_EXTRACTOR_VERSION
    scanned_message_count: int = 0
    stock_hit_message_count: int = 0
    raw_mention_count: int = 0
    source_broker_filtered_count: int = 0
    broad_list_mention_count: int = 0
    inserted_mention_count: int = 0
    effective_mention_count: int = 0
    repeated_mention_count: int = 0
    prewarm_trade_day_count: int = 0
    prewarm_daily_row_count: int = 0
    prewarm_skipped_day_count: int = 0
    prewarm_index_row_count: int = 0
    refreshed_count: int = 0
    pending_count: int = 0
    missing_price_count: int = 0
    failed_count: int = 0


class AnalystMentionSummaryRow(BaseModel):
    analyst_id: str
    analyst_display_name: str
    event_count: int = 0
    latest_event_time: datetime | None = None
    metrics: dict[str, float | int] = Field(default_factory=dict)


class AnalystMentionSummaryResult(BaseModel):
    start_time: datetime
    end_time: datetime
    windows: list[int] = Field(default_factory=list)
    row_count: int = 0
    rows: list[AnalystMentionSummaryRow] = Field(default_factory=list)


class AnalystMentionEvidenceItem(BaseModel):
    mention_id: str
    message_id: str
    analyst_id: str
    analyst_display_name: str
    ts_code: str
    stock_name: str
    message_time: datetime
    evidence_snippet: str
    stock_count_in_message: int = 1
    quality_flags: tuple[str, ...] = ()
    window_days: int
    status: MentionWindowStatus | None = None
    target_trade_date: str | None = None
    return_rate: float | None = None
    positive: bool | None = None
    excess_return_rate: float | None = None


class AnalystMentionEvidenceResult(BaseModel):
    start_time: datetime
    end_time: datetime
    window_days: int
    row_count: int = 0
    rows: list[AnalystMentionEvidenceItem] = Field(default_factory=list)


class AnalystMentionMessageEvidenceItem(BaseModel):
    message_id: str
    analyst_id: str
    analyst_display_name: str
    message_time: datetime
    raw_content: str
    stock_count: int = 0
    mentioned_stock_count: int = 0
    quality_flags: tuple[str, ...] = ()
    window_days: int
    metrics: dict[str, float | int] = Field(default_factory=dict)
    items: list[AnalystMentionEvidenceItem] = Field(default_factory=list)


class AnalystMentionMessageEvidenceResult(BaseModel):
    start_time: datetime
    end_time: datetime
    window_days: int
    row_count: int = 0
    rows: list[AnalystMentionMessageEvidenceItem] = Field(default_factory=list)
