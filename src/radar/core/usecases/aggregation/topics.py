from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageCategory, MessageSource
from radar.core.usecases.aggregation.models import AggregateTopicsResult
from radar.core.usecases.categories import normalize_derived_input_categories

AGGREGATE_EXTRACTOR_VERSION = "market-anchor-v1"


def aggregate_topics(
    config: RadarConfig,
    *,
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    categories: list[MessageCategory] | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = AGGREGATE_EXTRACTOR_VERSION,
    min_messages: int = 2,
    limit: int = 20,
    evidence_limit: int = 3,
) -> AggregateTopicsResult:
    """消息级 anchor 已移除，主题聚合暂不从本地词库生成候选。"""

    _ = (config, source, min_messages, limit, evidence_limit)
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if min_classification_confidence < 0 or min_classification_confidence > 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")

    category_values = normalize_derived_input_categories(categories)
    return AggregateTopicsResult(
        trade_date=trade_date,
        extractor_version=extractor_version,
        start_time=start_time,
        end_time=end_time,
        categories=category_values,
        min_classification_confidence=min_classification_confidence,
        scoped_message_count=0,
        anchored_message_count=0,
        topic_count=0,
        topics=[],
    )
