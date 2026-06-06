from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.messages.overview import MessageOverview, get_message_overview
from radar.core.organize import OrganizeClassificationFilters, OrganizeClassificationPage, list_classification_clusters
from radar.core.organize_aggregates import OrganizeAggregateFilters, OrganizeAggregatePage, list_aggregate_themes
from radar.core.store import connect, init_db
from radar.core.usecases.recommendation_backtest import (
    DEFAULT_BACKTEST_WINDOWS,
    RecommendationBacktestSummaryResult,
    summarize_recommendation_backtests,
)
from radar.core.usecases.strategy import StrategyDashboard, build_strategy_dashboard


class DashboardSummaryPayload(BaseModel):
    overview: MessageOverview
    classifications: OrganizeClassificationPage
    aggregates: OrganizeAggregatePage
    backtest: RecommendationBacktestSummaryResult
    strategy: StrategyDashboard


def build_dashboard_summary_payload(config: RadarConfig) -> DashboardSummaryPayload:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        overview = get_message_overview(conn, days=14, top_limit=8, anchor_limit=20)
        classifications = list_classification_clusters(
            conn,
            OrganizeClassificationFilters(evidence_limit=0, low_confidence_threshold=0.75),
        )
        aggregates = list_aggregate_themes(conn, OrganizeAggregateFilters(evidence_limit=0))
    finally:
        conn.close()

    end_time = datetime.now()
    start_time = end_time - timedelta(days=30)
    backtest = summarize_recommendation_backtests(
        config,
        start_time=start_time,
        end_time=end_time,
        group_by="analyst_sector",
        windows=list(DEFAULT_BACKTEST_WINDOWS),
        min_count=3,
        limit=200,
    )
    strategy = build_strategy_dashboard(config, days=30, recent_days=7, limit=3)
    return DashboardSummaryPayload(
        overview=overview,
        classifications=classifications,
        aggregates=aggregates,
        backtest=backtest,
        strategy=strategy,
    )
