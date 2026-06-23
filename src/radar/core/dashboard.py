from __future__ import annotations

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.messages.overview import MessageOverview, get_message_overview
from radar.core.organize import OrganizeClassificationFilters, OrganizeClassificationPage, list_classification_clusters
from radar.core.storage import connect, init_db


class DashboardSummaryPayload(BaseModel):
    overview: MessageOverview
    classifications: OrganizeClassificationPage


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

    return DashboardSummaryPayload(
        overview=overview,
        classifications=classifications,
    )
