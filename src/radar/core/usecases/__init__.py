"""Core use cases that orchestrate lower-level capabilities."""

from radar.core.usecases.aggregation import (
    AggregateTopicsResult,
    RefineAggregateTopicsResult,
    aggregate_topics,
    refine_aggregate_topics,
)
from radar.core.usecases.anchoring import AnchorRangeResult, anchor_messages_range
from radar.core.usecases.classification import (
    ClassifyMessagesResult,
    ClassifyRangeResult,
    classify_batch_with_llm,
    classify_messages,
    classify_messages_range,
)
from radar.core.usecases.ingest_wechat import (
    IngestRangeResult,
    IngestWindowResult,
    ingest_wechat_range,
    ingest_wechat_window,
)
from radar.core.usecases.smoke import SmokeResult, test_llm, test_market

__all__ = [
    "AnchorRangeResult",
    "AggregateTopicsResult",
    "RefineAggregateTopicsResult",
    "ClassifyMessagesResult",
    "ClassifyRangeResult",
    "IngestRangeResult",
    "IngestWindowResult",
    "SmokeResult",
    "aggregate_topics",
    "refine_aggregate_topics",
    "anchor_messages_range",
    "classify_batch_with_llm",
    "classify_messages",
    "classify_messages_range",
    "ingest_wechat_range",
    "ingest_wechat_window",
    "test_llm",
    "test_market",
]
