from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceRelationType = Literal["A化B", "prefix-anchor", "modifier-anchor", "anchor-extension", "other"]
SourceSignalStatus = Literal["source_seed", "spreading_watch", "mapped", "old_theme"]


class SourceStructure(BaseModel):
    structure_id: str
    message_id: str
    source: str = ""
    sender: str = ""
    group_name: str | None = None
    message_time: datetime
    is_candidate: bool = False
    anchor_span: str = ""
    modifier_span: str = ""
    novel_span: str = ""
    relation_type: SourceRelationType = "other"
    relation_evidence: str = ""
    ask_question: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reject_reason: str | None = None
    llm_provider: str | None = None
    prompt_version: str = ""
    extractor_version: str = ""
    created_at: datetime
    updated_at: datetime


class SourceSignalCandidate(BaseModel):
    signal_id: str
    status: SourceSignalStatus
    anchor_span: str
    modifier_span: str
    novel_span: str
    relation_type: SourceRelationType
    score: float
    novelty_strength: float
    earliness_score: float
    askability_score: float
    trade_score: float
    first_message_id: str
    first_seen_time: datetime
    first_sender: str
    first_group_name: str | None = None
    first_snippet: str = ""
    prior_anchor_mentions: int = 0
    prior_modifier_mentions: int = 0
    prior_exact_mentions: int = 0
    prior_combo_mentions: int = 0
    asof_mentions: int = 0
    asof_groups: int = 0
    asof_senders: int = 0
    followup_groups: int = 0
    followup_senders: int = 0
    mapped_stocks: list[str] = Field(default_factory=list)
    ask_question: str = ""
    evidence: list[str] = Field(default_factory=list)


class SourceSignalResult(BaseModel):
    start_time: datetime
    end_time: datetime
    as_of_time: datetime
    lookback_days: int
    scanned_count: int
    candidate_count: int
    candidates: list[SourceSignalCandidate] = Field(default_factory=list)
