from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

BacktestAction = Literal["bullish", "bearish"]
BacktestWindowStatus = Literal["pending", "succeeded", "missing_price", "failed"]
BacktestGroupBy = Literal[
    "source",
    "source_stock",
    "stock",
    "analyst",
    "analyst_stock",
    "sector",
    "analyst_sector",
]

DEFAULT_BACKTEST_WINDOWS: tuple[int, ...] = (1, 2, 3, 5)
DEFAULT_BENCHMARK_TS_CODE = "000300.SH"


class RecommendationEvent(BaseModel):
    event_id: str
    message_id: str
    source: str
    source_candidate: str
    analyst_id: str | None = None
    analyst_display_name: str | None = None
    analyst_alias_key: str | None = None
    group_name: str | None = None
    category: str
    classification_confidence: float
    ts_code: str
    stock_name: str
    action: BacktestAction
    message_time: datetime
    event_date: str
    extractor_version: str
    anchor_confidence: float
    sector_anchor_id: str | None = None
    sector_anchor_type: str | None = None
    sector_name: str | None = None
    sector_confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class BacktestWindowResult(BaseModel):
    event_id: str
    window_days: int
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    base_trade_date: str | None = None
    target_trade_date: str | None = None
    base_close: float | None = None
    target_close: float | None = None
    return_rate: float | None = None
    win: bool | None = None
    benchmark_base_close: float | None = None
    benchmark_target_close: float | None = None
    benchmark_return_rate: float | None = None
    excess_return_rate: float | None = None
    status: BacktestWindowStatus
    error_message: str | None = None
    updated_at: datetime


class RecommendationBacktestRefreshResult(BaseModel):
    run_id: str
    as_of: date
    start_time: datetime
    end_time: datetime
    windows: list[int] = Field(default_factory=list)
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE
    event_count: int = 0
    inserted_event_count: int = 0
    refreshed_count: int = 0
    skipped_complete_count: int = 0
    pending_count: int = 0
    missing_price_count: int = 0
    failed_count: int = 0


class RecommendationBacktestSummaryRow(BaseModel):
    key: str
    source_candidate: str | None = None
    analyst_id: str | None = None
    analyst_display_name: str | None = None
    ts_code: str | None = None
    stock_name: str | None = None
    sector_anchor_type: str | None = None
    sector_name: str | None = None
    event_count: int = 0
    metrics: dict[str, float | int] = Field(default_factory=dict)


class RecommendationBacktestSummaryResult(BaseModel):
    start_time: datetime
    end_time: datetime
    group_by: BacktestGroupBy
    windows: list[int] = Field(default_factory=list)
    row_count: int = 0
    rows: list[RecommendationBacktestSummaryRow] = Field(default_factory=list)
