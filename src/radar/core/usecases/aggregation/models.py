from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.models import MessageAnchorType, MessageCategory


class RelatedStock(BaseModel):
    name: str
    count: int


class AggregateTopicEvidence(BaseModel):
    message_id: str
    message_time: datetime
    category: MessageCategory
    classification_confidence: float
    anchor_confidence: float
    sender: str
    group_name: str | None = None
    raw_content: str
    stocks: list[str] = Field(default_factory=list)


class AggregateTopic(BaseModel):
    name: str
    anchor_types: list[MessageAnchorType]
    message_count: int
    anchor_count: int
    score: float
    latest_time: datetime
    category_distribution: dict[MessageCategory, int]
    related_stocks: list[RelatedStock]
    evidence: list[AggregateTopicEvidence]


class AggregateTopicsResult(BaseModel):
    trade_date: str
    extractor_version: str
    start_time: datetime
    end_time: datetime
    categories: list[MessageCategory]
    min_classification_confidence: float
    scoped_message_count: int
    anchored_message_count: int
    topic_count: int
    topics: list[AggregateTopic]


class RefinedThemeStock(BaseModel):
    name: str
    reason: str = ""
    confidence: float = 0.0


class RefinedTheme(BaseModel):
    theme_name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    investment_logic: str = ""
    catalysts: list[str] = Field(default_factory=list)
    related_stocks: list[RefinedThemeStock] = Field(default_factory=list)
    evidence_message_ids: list[str] = Field(default_factory=list)
    novelty: str = "unknown"
    confidence: float = 0.0
    actionability_score: float = 0.0
    risk_notes: list[str] = Field(default_factory=list)
    merge_from_candidate_ids: list[str] = Field(default_factory=list)


class RefineAggregateTopicsResult(BaseModel):
    run_id: str
    input_hash: str
    status: str
    trade_date: str
    extractor_version: str
    prompt_version: str
    candidate_count: int
    theme_count: int
    llm_batch_count: int = 0
    failed_llm_batches: int = 0
    max_concurrency: int = 0
    local_result: AggregateTopicsResult
    themes: list[RefinedTheme]
