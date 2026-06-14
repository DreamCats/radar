from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


HIGH_VALUE_CATEGORIES = ("research", "event", "recommendation", "industry")
PROMPT_VERSION = "stock-evidence-chain-v3"
STAGES = ("lead", "seed", "formed", "spreading", "pricing", "crowded")


@dataclass(frozen=True)
class Stock:
    ts_code: str
    symbol: str
    name: str


@dataclass(frozen=True)
class MessageRow:
    message_id: str
    source: str
    sender: str
    message_time: datetime
    raw_content: str
    group_name: str | None
    category: str | None

    @property
    def conversation(self) -> str:
        return self.group_name or self.sender


@dataclass(frozen=True)
class StockMention:
    stock: Stock
    message: MessageRow
    fingerprint: str
    evidence_families: tuple[str, ...]
    evidence_score: int


@dataclass
class StockCandidate:
    stock: Stock
    trigger_count: int = 0
    unique_fingerprints: set[str] = field(default_factory=set)
    senders: set[str] = field(default_factory=set)
    conversations: set[str] = field(default_factory=set)
    evidence_score: int = 0
    family_counts: dict[str, int] = field(default_factory=dict)
    channels: set[str] = field(default_factory=set)

    @property
    def unique_trigger_count(self) -> int:
        return len(self.unique_fingerprints)

    @property
    def sender_count(self) -> int:
        return len(self.senders)

    @property
    def conversation_count(self) -> int:
        return len(self.conversations)

    @property
    def rank_key(self) -> tuple[int, int, int, int, int]:
        return (
            len(self.channels),
            self.unique_trigger_count,
            self.evidence_score,
            self.conversation_count,
            self.trigger_count,
        )


@dataclass(frozen=True)
class MarketPoint:
    trade_date: str
    close: float
    pct_chg: float | None
    amount: float | None
    amount_ratio_5d: float | None
    tag: str


@dataclass(frozen=True)
class MarketEvidence:
    points: list[MarketPoint]
    summary: dict[str, Any]


@dataclass(frozen=True)
class EvidencePack:
    candidate: StockCandidate
    evidence: list[StockMention]
    market: MarketEvidence | None = None


@dataclass(frozen=True)
class Judgement:
    stage: str
    confidence: float | None
    summary: str
    raw_text: str
    result: dict[str, object]
    provider: str | None
    model: str | None
