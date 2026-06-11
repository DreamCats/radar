from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

LIFECYCLE_DIGEST_SCOPE_TYPE = "stock_opportunity"


class StockEvidenceLifecycleDigestContext(BaseModel):
    scope_key: str
    theme_id: str | None = None
    theme_name: str | None = None
    stage_label: str | None = None
    recognition_label: str | None = None
    one_line: str = ""
    timeline: list[str] = Field(default_factory=list)
    stage_reason: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risk: list[str] = Field(default_factory=list)
    next_watch: list[str] = Field(default_factory=list)
    evidence_signature: str
    message_hash: str | None = None
    market_hash: str | None = None
    theme_hash: str | None = None
    recognition_hash: str | None = None
    backtest_hash: str | None = None
    lifecycle_package_hash: str | None = None
    updated_at: datetime


class LifecycleDigestHashes(BaseModel):
    message_hash: str
    market_hash: str
    theme_hash: str
    recognition_hash: str
    backtest_hash: str
    lifecycle_package_hash: str


class LifecycleDigestPreviewItem(BaseModel):
    scope_key: str
    ts_code: str
    stock_name: str
    theme_id: str | None = None
    theme_name: str | None = None
    stage_label: str
    recognition_label: str
    action: str
    reason: str
    evidence_signature: str
    hashes: LifecycleDigestHashes
    changed_hashes: list[str] = Field(default_factory=list)


class LifecycleDigestPreview(BaseModel):
    as_of_time: datetime | None = None
    scanned_count: int = 0
    processable_count: int = 0
    pending_count: int = 0
    skipped_count: int = 0
    estimated_llm_calls: int = 0
    items: list[LifecycleDigestPreviewItem] = Field(default_factory=list)


class LifecycleDigestRunResult(BaseModel):
    as_of_time: datetime | None = None
    scanned_count: int = 0
    processable_count: int = 0
    pending_count: int = 0
    generated_count: int = 0
    reused_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    rerun_reason_counts: dict[str, int] = Field(default_factory=dict)
