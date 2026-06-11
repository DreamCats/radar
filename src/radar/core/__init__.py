"""Shared core used by CLI and Web server."""

from radar.core.config import RadarConfig
from radar.core.llm import LlmConfigError, chat, chat_json, chat_json_list
from radar.core.messages import MessageFilters, MessagePage, list_messages
from radar.core.market import (
    EnsureMarketAnchorsResult,
    MarketAnchor,
    RefreshMarketAnchorDerivativesResult,
    RefreshMarketAnchorsResult,
    ensure_market_anchors,
    refresh_market_anchor_derivatives,
    refresh_market_anchors,
)
from radar.core.market import RefreshMarketThemeNormalizationResult, refresh_market_theme_normalization
from radar.core.models import MessageSource, RawMessage
from radar.core.organize import (
    OrganizeClassificationCluster,
    OrganizeClassificationFilters,
    OrganizeClassificationPage,
    OrganizeClassificationSummary,
    OrganizeEvidenceMessage,
    list_classification_clusters,
)
from radar.core.storage import RunRecord, fail_run, finish_run, get_run, start_run, update_run_progress
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.tushare import (
    TushareApiError,
    TushareConfigError,
    TushareError,
    TushareHttpError,
    call as call_tushare,
    resolve_stock,
)
from radar.core.usecases import (
    IngestRangeResult,
    IngestWindowResult,
    SmokeResult,
    ingest_wechat_range,
    ingest_wechat_window,
    test_llm,
    test_market,
)

__all__ = [
    "MessageFilters",
    "MessagePage",
    "MessageSource",
    "MarketAnchor",
    "EnsureMarketAnchorsResult",
    "OrganizeClassificationCluster",
    "OrganizeClassificationFilters",
    "OrganizeClassificationPage",
    "OrganizeClassificationSummary",
    "OrganizeEvidenceMessage",
    "RadarConfig",
    "RawMessage",
    "RefreshMarketAnchorDerivativesResult",
    "RefreshMarketAnchorsResult",
    "RefreshMarketThemeNormalizationResult",
    "RunRecord",
    "TushareApiError",
    "TushareConfigError",
    "TushareError",
    "TushareHttpError",
    "IngestRangeResult",
    "IngestWindowResult",
    "LlmConfigError",
    "SmokeResult",
    "chat",
    "chat_json",
    "chat_json_list",
    "connect",
    "fail_run",
    "finish_run",
    "get_run",
    "call_tushare",
    "ingest_wechat_range",
    "ingest_wechat_window",
    "init_db",
    "list_messages",
    "list_classification_clusters",
    "resolve_stock",
    "ensure_market_anchors",
    "refresh_market_anchor_derivatives",
    "refresh_market_anchors",
    "refresh_market_theme_normalization",
    "start_run",
    "test_llm",
    "test_market",
    "update_run_progress",
    "upsert_messages",
]
