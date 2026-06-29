from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.messages import CatalystStockMention, CatalystTermHit
from radar.core.models import MessageSource

ConceptSource = Literal["ths", "dc", "none"]


class PremarketSignalQuery(BaseModel):
    start_time: datetime
    end_time: datetime
    limit: int = Field(default=30, ge=1, le=100)


class PremarketEvidence(BaseModel):
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    message_time: datetime
    raw_content: str
    matched_terms: list[CatalystTermHit] = Field(default_factory=list)
    stock_mentions: list[CatalystStockMention] = Field(default_factory=list)


class PremarketStockRank(BaseModel):
    ts_code: str | None = None
    stock_name: str
    mention_count: int
    person_count: int
    message_count: int
    first_time: datetime
    latest_time: datetime
    catalyst_terms: list[CatalystTermHit] = Field(default_factory=list)


class PremarketConceptRank(BaseModel):
    concept_code: str
    concept_name: str
    source: ConceptSource
    score: float
    velocity_score: float = 0
    early_mention_count: int = 0
    late_mention_count: int = 0
    stock_count: int
    mention_count: int
    person_count: int
    message_count: int
    top_stocks: list[PremarketStockRank] = Field(default_factory=list)
    catalyst_terms: list[CatalystTermHit] = Field(default_factory=list)
    evidence: list[PremarketEvidence] = Field(default_factory=list)


class PremarketSignalSummary(BaseModel):
    start_time: datetime
    end_time: datetime
    messages_scanned: int
    catalyst_items: int
    stock_mentions: int
    dedup_person_stock_mentions: int
    concept_source: ConceptSource
    concept_count: int
    ranked_concept_count: int


class PremarketConcentrationItem(BaseModel):
    concept_count: int
    covered_dedup_person_stock_mentions: int
    total_dedup_person_stock_mentions: int
    coverage_pct: float


class PremarketTimeBucket(BaseModel):
    start_time: datetime
    end_time: datetime
    catalyst_items: int = 0
    dedup_person_stock_mentions: int = 0


class PremarketSignalResult(BaseModel):
    query: PremarketSignalQuery
    summary: PremarketSignalSummary
    concepts: list[PremarketConceptRank] = Field(default_factory=list)
    top_concepts: list[PremarketConceptRank] = Field(default_factory=list)
    bottom_concepts: list[PremarketConceptRank] = Field(default_factory=list)
    velocity_concepts: list[PremarketConceptRank] = Field(default_factory=list)
    concentration: list[PremarketConcentrationItem] = Field(default_factory=list)
    time_buckets: list[PremarketTimeBucket] = Field(default_factory=list)
