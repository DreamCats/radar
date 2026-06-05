from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MessageSource = Literal["个人消息", "个人群"]
MessageCategory = Literal[
    "research",
    "recommendation",
    "event",
    "industry",
    "tool_ad",
    "chat",
    "unknown",
]
ClassificationStatus = Literal["auto", "needs_review", "confirmed", "ignored"]
ClassifierType = Literal["rule", "llm", "manual"]
ClassificationRetryMode = Literal["needs_review", "unknown", "low_confidence"]
MessageAnchorType = Literal["stock", "concept", "industry", "theme"]


class RawMessage(BaseModel):
    """标准化后的微信消息，是 core 内部和 SQLite 的基础数据单元。"""

    message_id: str
    source: MessageSource
    sender: str
    message_time: datetime
    raw_content: str
    fetch_time: datetime
    fetch_window: str
    group_name: str | None = None


class MessageClassification(BaseModel):
    """原始消息的派生分类结果；原文仍以 messages 表为准。"""

    message_id: str
    category: MessageCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    status: ClassificationStatus = "auto"
    classifier_type: ClassifierType = "rule"
    llm_provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    classifier_version: str = "rule-v1"
    created_at: datetime
    updated_at: datetime


class MessageAnchor(BaseModel):
    """原始消息命中的市场 anchor；用于后续主题聚合的结构化抓手。"""

    message_id: str
    anchor_id: str
    anchor_type: MessageAnchorType
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[dict[str, object]] = Field(default_factory=list)
    extractor_version: str
    trade_date: str
    created_at: datetime
    updated_at: datetime


class WechatApiMessage(BaseModel):
    """微信 API 原始字段是中文，单独建模便于隔离外部格式变化。"""

    sender: str = Field(alias="发送人")
    time: str = Field(alias="时间")
    content: str = Field(alias="内容")
    group_name: str | None = Field(default=None, alias="群名称")
