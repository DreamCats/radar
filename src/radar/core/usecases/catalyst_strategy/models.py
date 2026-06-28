from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.models import MessageSource


class CatalystStrategyEvidence(BaseModel):
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    message_time: datetime
    latest_message_time: datetime
    content: str
    matched_terms: list[str] = Field(default_factory=list)
    duplicate_count: int = 1


class FinancialTrendPoint(BaseModel):
    period: str
    revenue_yi: float | None = None
    net_profit_yi: float | None = None


class MarketSnapshot(BaseModel):
    ts_code: str | None = None
    stock_name: str
    realtime_price: float | None = None
    realtime_at: str | None = None
    realtime_source: str | None = None
    last_close: float | None = None
    last_trade_date: str | None = None
    total_share_10000: float | None = None
    total_mv_yi: float | None = None
    circ_mv_yi: float | None = None
    pe: float | None = None
    pe_ttm: float | None = None
    estimated_total_mv_yi: float | None = None
    estimated_pe: float | None = None
    estimated_pe_ttm: float | None = None
    implied_net_profit_ttm_yi: float | None = None
    pe_ttm_percentile_60d: float | None = None
    pe_ttm_percentile_120d: float | None = None
    pe_ttm_percentile_250d: float | None = None
    latest_financial_period: str | None = None
    latest_revenue_yi: float | None = None
    latest_net_profit_yi: float | None = None
    financial_trend: list[FinancialTrendPoint] = Field(default_factory=list)
    price_basis: str = "unknown"
    valuation_basis: str = "missing"
    error: str | None = None
    financial_error: str | None = None


class CatalystStockContext(BaseModel):
    stock_key: str
    ts_code: str | None = None
    stock_name: str
    first_message_time: datetime
    latest_message_time: datetime
    evidence: list[CatalystStrategyEvidence] = Field(default_factory=list)
    market_snapshot: MarketSnapshot | None = None


class CatalystStockAnalysis(BaseModel):
    stock_key: str
    ts_code: str | None = None
    stock_name: str
    summary: list[str] = Field(default_factory=list)
    valuation_status: Literal["provided", "scenario", "skipped", "error"] = "skipped"
    valuation_text: str = ""
    target_market_cap_yi: float | None = None
    target_price: float | None = None
    upside_pct: float | None = None
    confidence: str | None = None
    risks: list[str] = Field(default_factory=list)
    raw_response: dict[str, object] | None = None


class CatalystStrategyReport(BaseModel):
    generated_at: datetime
    start_time: datetime
    end_time: datetime
    total_feed_items: int
    total_stocks: int
    stocks: list[CatalystStockContext] = Field(default_factory=list)
    analyses: list[CatalystStockAnalysis] = Field(default_factory=list)


class CatalystStrategyRunResult(BaseModel):
    report: CatalystStrategyReport
    local_html_path: Path
    published_url: str | None = None
    bark_sent: bool = False
