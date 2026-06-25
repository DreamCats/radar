from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from radar.core.models import MessageSource


class CatalystCategory(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#5e6ad2", min_length=1, max_length=32)
    terms: list[str] = Field(default_factory=list)

    @field_validator("terms")
    @classmethod
    def normalize_terms(cls, value: list[str]) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for term in value:
            cleaned = str(term).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            terms.append(cleaned)
        return terms


class CatalystTermLibrary(BaseModel):
    version: int = 1
    categories: list[CatalystCategory] = Field(default_factory=list)


class CatalystTermHit(BaseModel):
    category_id: str
    category_name: str
    color: str
    term: str


class CatalystStockMention(BaseModel):
    ts_code: str | None = None
    stock_name: str


class CatalystDuplicateSource(BaseModel):
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    message_time: datetime
    latest_message_time: datetime | None = None
    message_count: int = 1


class CatalystEvidenceMessage(BaseModel):
    message_id: str
    message_time: datetime
    raw_content: str
    matched_terms: list[CatalystTermHit] = Field(default_factory=list)


class CatalystFeedItem(BaseModel):
    key: str
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    first_message_time: datetime
    latest_message_time: datetime
    raw_content: str
    normalized_content_hash: str
    message_count: int = 1
    messages: list[CatalystEvidenceMessage] = Field(default_factory=list)
    matched_terms: list[CatalystTermHit]
    stock_mentions: list[CatalystStockMention] = Field(default_factory=list)
    duplicate_count: int
    duplicate_sources: list[CatalystDuplicateSource]


class CatalystFeedSummary(BaseModel):
    total_items: int
    total_messages: int
    duplicate_messages: int
    available_total_items: int
    category_counts: dict[str, int] = Field(default_factory=dict)
    term_counts: dict[str, dict[str, int]] = Field(default_factory=dict)


class CatalystFeedPage(BaseModel):
    items: list[CatalystFeedItem]
    summary: CatalystFeedSummary
    next_cursor_time: datetime | None = None
    next_cursor_key: str | None = None


class CatalystFeedFilters(BaseModel):
    start_time: datetime
    end_time: datetime
    source: MessageSource | None = None
    group_name: str | None = None
    category_ids: list[str] = Field(default_factory=list)
    keyword: str | None = None
    dedupe: bool = True
    cursor_time: datetime | None = None
    cursor_key: str | None = None
    limit: int = Field(default=60, ge=1, le=200)


CatalystStockDetector = Callable[[str], list[CatalystStockMention]]
