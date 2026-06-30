from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from radar.core.models import MessageSource


class CatalystValuationEvidence(BaseModel):
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    message_time: datetime
    latest_message_time: datetime
    content: str
    matched_terms: list[str] = Field(default_factory=list)
    valuation_terms: list[str] = Field(default_factory=list)
    valuation_numbers: list[str] = Field(default_factory=list)
    stock_mentions_count: int = 1
    duplicate_count: int = 1


class CatalystValuationStockContext(BaseModel):
    stock_key: str
    ts_code: str | None = None
    stock_name: str
    first_message_time: datetime
    latest_message_time: datetime
    evidence: list[CatalystValuationEvidence] = Field(default_factory=list)


class CatalystValuationReport(BaseModel):
    generated_at: datetime
    start_time: datetime
    end_time: datetime
    total_feed_items: int
    total_candidate_stocks: int
    total_stocks: int
    stocks: list[CatalystValuationStockContext] = Field(default_factory=list)


class CatalystValuationReportRunResult(BaseModel):
    report: CatalystValuationReport
    local_html_path: Path
    published_url: str | None = None
    bark_sent: bool = False
    bark_error: str | None = None


CatalystStockContext = CatalystValuationStockContext
