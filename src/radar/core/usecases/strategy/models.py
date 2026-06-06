from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import MessageAnchorType

StrategyAttentionLevel = Literal["重点关注", "继续验证", "风险升高", "样本不足", "过度扩散"]
StrategyStockLifecycleState = Literal["初现", "发酵中", "已兑现", "回调再看", "缺少价格"]


class StrategyRelatedStock(BaseModel):
    stock_name: str
    ts_code: str
    event_count: int
    source_count: int = 0
    win_rate_t5: float | None = None
    average_excess_return_t5: float | None = None
    first_seen_time: datetime | None = None
    latest_message_time: datetime | None = None
    lifecycle_state: StrategyStockLifecycleState | None = None
    lifecycle_reason: str | None = None
    signal_age_days: int | None = None
    price_return_since_first_seen: float | None = None
    recent_price_return_3d: float | None = None
    drawdown_from_high_since_first_seen: float | None = None


class StrategySourceSignal(BaseModel):
    name: str
    mention_count: int = 0
    event_count: int = 0
    win_rate_t5: float | None = None
    average_excess_return_t5: float | None = None
    latest_message_time: datetime | None = None


class StrategyThemeBrief(BaseModel):
    theme_name: str
    confidence: float = 0.0
    actionability_score: float = 0.0
    catalysts: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class StrategyBacktestMetric(BaseModel):
    event_count: int = 0
    matured_event_count: int = 0
    pending_event_count: int = 0
    win_rate_t5: float | None = None
    average_excess_return_t5: float | None = None


class StrategyOpportunity(BaseModel):
    key: str
    name: str
    anchor_type: MessageAnchorType
    attention_level: StrategyAttentionLevel
    score: float
    reliability_score: float
    reason: str
    risk_summary: str
    recent_message_count: int
    previous_message_count: int
    acceleration: float
    sender_count: int
    group_count: int
    high_value_count: int
    high_value_ratio: float
    recommendation_count: int
    research_count: int
    industry_count: int
    catalyst_count: int
    risk_count: int
    catalyst_terms: list[str] = Field(default_factory=list)
    risk_terms: list[str] = Field(default_factory=list)
    t5_event_count: int = 0
    win_rate_t5: float | None = None
    average_excess_return_t5: float | None = None
    opportunity_backtest: StrategyBacktestMetric = Field(default_factory=StrategyBacktestMetric)
    selected_stock_backtest: StrategyBacktestMetric = Field(default_factory=StrategyBacktestMetric)
    latest_message_time: datetime
    related_stocks: list[StrategyRelatedStock] = Field(default_factory=list)
    top_sources: list[StrategySourceSignal] = Field(default_factory=list)
    matched_themes: list[StrategyThemeBrief] = Field(default_factory=list)


class StrategyStockCandidate(BaseModel):
    stock_name: str
    ts_code: str
    event_count: int
    source_count: int
    sector_names: list[str] = Field(default_factory=list)
    win_rate_t5: float | None = None
    average_excess_return_t5: float | None = None
    latest_message_time: datetime | None = None


class StrategyDashboard(BaseModel):
    start_time: datetime
    end_time: datetime
    recent_start_time: datetime
    generated_at: datetime
    opportunity_count: int
    opportunities: list[StrategyOpportunity] = Field(default_factory=list)
    source_quality: list[StrategySourceSignal] = Field(default_factory=list)
    stock_candidates: list[StrategyStockCandidate] = Field(default_factory=list)
