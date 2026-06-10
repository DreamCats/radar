from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.messages.overview import MessageOverview, get_message_overview
from radar.core.organize import OrganizeClassificationFilters, OrganizeClassificationPage, list_classification_clusters
from radar.core.store import connect, init_db
from radar.core.usecases.recommendation_backtest import (
    DEFAULT_BACKTEST_WINDOWS,
    RecommendationBacktestSummaryResult,
    summarize_recommendation_backtests,
)


class DashboardSummaryPayload(BaseModel):
    overview: MessageOverview
    classifications: OrganizeClassificationPage
    backtest: RecommendationBacktestSummaryResult


def build_dashboard_summary_payload(config: RadarConfig) -> DashboardSummaryPayload:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        overview = get_message_overview(conn, days=14, top_limit=8)
        classifications = list_classification_clusters(
            conn,
            OrganizeClassificationFilters(evidence_limit=0, low_confidence_threshold=0.75),
        )
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
    return DashboardSummaryPayload(
        overview=overview,
        classifications=classifications,
        backtest=backtest,
    )
