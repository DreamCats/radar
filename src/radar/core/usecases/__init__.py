"""Core use cases that orchestrate lower-level capabilities."""

from radar.core.usecases.aggregation import (
    AggregateTopicsResult,
    RefineAggregateTopicsResult,
    aggregate_topics,
    refine_aggregate_topics,
)
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
from radar.core.usecases.recommendation_backtest import (
    RecommendationBacktestRefreshResult,
    RecommendationBacktestSummaryResult,
    refresh_recommendation_backtests,
    summarize_recommendation_backtests,
)
from radar.core.usecases.smoke import SmokeResult, test_llm, test_market

__all__ = [
    "AggregateTopicsResult",
    "RefineAggregateTopicsResult",
    "ClassifyMessagesResult",
    "ClassifyRangeResult",
    "IngestRangeResult",
    "IngestWindowResult",
    "RecommendationBacktestRefreshResult",
    "RecommendationBacktestSummaryResult",
    "SmokeResult",
    "aggregate_topics",
    "refine_aggregate_topics",
    "classify_batch_with_llm",
    "classify_messages",
    "classify_messages_range",
    "ingest_wechat_range",
    "ingest_wechat_window",
    "refresh_recommendation_backtests",
    "summarize_recommendation_backtests",
    "test_llm",
    "test_market",
]
