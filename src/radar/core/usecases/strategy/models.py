from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import MessageAnchorType

StrategyAttentionLevel = Literal["重点关注", "继续验证", "风险升高", "样本不足", "过度扩散"]
StrategyStockLifecycleState = Literal["初现", "发酵中", "已兑现", "回调再看", "缺少价格"]
StrategyStockPricePosition = Literal["趋势健康", "可观察", "震荡观察", "回撤偏大", "短线偏弱", "首现后走弱", "缺少价格"]
StrategyEventCredibilityLevel = Literal["高可信", "中可信", "低可信", "待验证"]
StrategyStockDecisionBucket = Literal["今日可关注", "观察等待", "已兑现复盘"]


class StrategyEventCredibility(BaseModel):
    score: float = 0.0
    level: StrategyEventCredibilityLevel = "待验证"
    first_source_name: str | None = None
    first_group_name: str | None = None
    first_event_time: datetime | None = None
    first_message_stock_count: int = 0
    source_matured_event_count: int = 0
    source_win_rate_t5: float | None = None
    source_average_excess_return_t5: float | None = None
    logic_hit_count: int = 0
    hype_hit_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


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
    price_position: StrategyStockPricePosition | None = None
    realtime_score: float = 0.0
    event_credibility: StrategyEventCredibility | None = None
    decision_bucket: StrategyStockDecisionBucket = "观察等待"
    decision_reason: str | None = None


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
    first_seen_time: datetime | None = None
    latest_message_time: datetime | None = None
    lifecycle_state: StrategyStockLifecycleState | None = None
    lifecycle_reason: str | None = None
    signal_age_days: int | None = None
    price_return_since_first_seen: float | None = None
    recent_price_return_3d: float | None = None
    drawdown_from_high_since_first_seen: float | None = None
    price_position: StrategyStockPricePosition | None = None
    realtime_score: float = 0.0
    event_credibility: StrategyEventCredibility | None = None
    decision_bucket: StrategyStockDecisionBucket = "观察等待"
    decision_reason: str | None = None


class StrategyDashboard(BaseModel):
    start_time: datetime
    end_time: datetime
    recent_start_time: datetime
    generated_at: datetime
    opportunity_count: int
    opportunities: list[StrategyOpportunity] = Field(default_factory=list)
    source_quality: list[StrategySourceSignal] = Field(default_factory=list)
    stock_candidates: list[StrategyStockCandidate] = Field(default_factory=list)


class LeadSignalWindow(BaseModel):
    window_days: int
    target_trade_date: str | None = None
    target_close: float | None = None
    return_rate: float | None = None
    excess_return_rate: float | None = None


class LeadSignalBucket(BaseModel):
    label: str
    window_days: int
    event_count: int = 0
    average_return: float | None = None
    average_excess_return: float | None = None
    up_rate: float | None = None


class LeadSignalSourceStat(BaseModel):
    source_name: str
    event_count: int = 0
    non_hot_event_count: int = 0
    pre_rise_event_count: int = 0
    strong_pre_rise_event_count: int = 0
    limit_like_event_count: int = 0
    pre_rise_rate: float | None = None
    average_t1_return: float | None = None
    average_t1_excess_return: float | None = None
    latest_message_time: datetime | None = None


class LeadSignalSample(BaseModel):
    event_date: str
    signal_label: str = ""
    stock_name: str
    ts_code: str
    message_day_pct_chg: float | None = None
    base_trade_date: str | None = None
    base_close: float | None = None
    first_message_time: datetime
    event_count: int = 0
    source_names: list[str] = Field(default_factory=list)
    windows: list[LeadSignalWindow] = Field(default_factory=list)


class LeadSignalSummary(BaseModel):
    start_time: datetime
    end_time: datetime
    generated_at: datetime
    as_of_date: str
    available_dates: list[str] = Field(default_factory=list)
    validation_days: int
    benchmark_ts_code: str
    message_day_max_pct: float
    strong_return_pct: float
    limit_like_pct: float
    day_event_count: int = 0
    day_stock_day_count: int = 0
    day_non_hot_event_count: int = 0
    day_non_hot_stock_day_count: int = 0
    day_limit_like_event_count: int = 0
    day_limit_like_stock_day_count: int = 0
    event_count: int = 0
    stock_day_count: int = 0
    non_hot_event_count: int = 0
    non_hot_stock_day_count: int = 0
    pre_rise_event_count: int = 0
    pre_rise_stock_day_count: int = 0
    strong_pre_rise_event_count: int = 0
    strong_pre_rise_stock_day_count: int = 0
    limit_like_event_count: int = 0
    limit_like_stock_day_count: int = 0
    buckets: list[LeadSignalBucket] = Field(default_factory=list)
    source_stats: list[LeadSignalSourceStat] = Field(default_factory=list)
    samples: list[LeadSignalSample] = Field(default_factory=list)
