from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from radar.core.usecases.stock_evidence_chain.lifecycle_models import StockEvidenceLifecycleDigestContext
from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)
from radar.core.usecases.stock_evidence_chain.review import StockEvidenceReviewContext


class StockEvidenceMarketPoint(BaseModel):
    trade_date: str
    close: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    amount_ratio_5d: float | None = None
    tag: str | None = None


class StockEvidenceMessage(BaseModel):
    message_id: str | None = None
    time: str | None = None
    type: str | None = None
    evidence: str | None = None
    sender: str | None = None
    group_name: str | None = None
    raw_content: str | None = None


class StockEvidenceMarketValidation(BaseModel):
    status: str = "unknown"
    label: str = "待判断"
    note: str = ""
    latest_trade_date: str | None = None
    current_first_time: str | None = None
    current_last_time: str | None = None


class StockEvidenceChainItem(BaseModel):
    ts_code: str
    stock_name: str
    stage: str
    stage_label: str
    confidence: float | None = None
    rank: int | None = None
    summary: str
    trigger_count: int
    unique_trigger_count: int
    sender_count: int
    conversation_count: int
    evidence_count: int
    channels: list[str] = Field(default_factory=list)
    family_counts: dict[str, int] = Field(default_factory=dict)
    why: list[str] = Field(default_factory=list)
    incremental_valid: bool | None = None
    incremental_points: list[str] = Field(default_factory=list)
    pricing_risk: str | None = None
    crowding_risk: str | None = None
    watch_next: list[str] = Field(default_factory=list)
    current_triggers: list[StockEvidenceMessage] = Field(default_factory=list)
    evidence_chain: list[StockEvidenceMessage] = Field(default_factory=list)
    market_summary: dict[str, Any] = Field(default_factory=dict)
    market_points: list[StockEvidenceMarketPoint] = Field(default_factory=list)
    market_validation: StockEvidenceMarketValidation = Field(default_factory=StockEvidenceMarketValidation)
    themes: list[StockEvidenceThemeContext] = Field(default_factory=list)
    primary_theme: StockEvidenceThemeContext | None = None
    recognition: StockEvidenceRecognitionContext = Field(default_factory=StockEvidenceRecognitionContext)
    review: StockEvidenceReviewContext = Field(default_factory=StockEvidenceReviewContext)
    lifecycle_digest: StockEvidenceLifecycleDigestContext | None = None
    updated_at: datetime


class StockEvidenceChainDashboard(BaseModel):
    as_of_time: datetime | None = None
    window_start_time: datetime | None = None
    evidence_start_time: datetime | None = None
    generated_at: datetime
    item_count: int = 0
    stage_counts: dict[str, int] = Field(default_factory=dict)
    items: list[StockEvidenceChainItem] = Field(default_factory=list)


class StockEvidenceChainSnapshot(BaseModel):
    as_of_time: datetime
    window_start_time: datetime | None = None
    evidence_start_time: datetime | None = None
    item_count: int = 0
    updated_at: datetime | None = None


class StockEvidenceChainSnapshotList(BaseModel):
    items: list[StockEvidenceChainSnapshot] = Field(default_factory=list)
