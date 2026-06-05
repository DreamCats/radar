from __future__ import annotations

import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.models import MessageCategory, MessageSource


CATEGORY_LABELS: dict[MessageCategory, str] = {
    "research": "研究观点",
    "recommendation": "投资推荐",
    "event": "会议活动",
    "industry": "产业变化",
    "tool_ad": "研究观点",
    "chat": "闲聊低噪",
    "unknown": "待确认",
}

_DISPLAY_CATEGORY_SQL = "CASE WHEN c.category = 'tool_ad' THEN 'research' ELSE c.category END"
_CATEGORY_ORDER: tuple[MessageCategory, ...] = (
    "recommendation",
    "research",
    "industry",
    "event",
    "chat",
)
_ACTIONABLE_DISPLAY_CATEGORIES: tuple[MessageCategory, ...] = (
    "recommendation",
    "research",
    "industry",
    "event",
)
ORGANIZE_DISPLAY_CONFIDENCE_THRESHOLD = 0.75


class OrganizeClassificationFilters(BaseModel):
    """整理页第一版：基于单条消息分类结果做只读聚合。"""

    source: MessageSource | None = None
    category: MessageCategory | None = None
    keyword: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    evidence_limit: int = Field(default=8, ge=0, le=30)
    low_confidence_threshold: float = Field(default=ORGANIZE_DISPLAY_CONFIDENCE_THRESHOLD, ge=0.0, le=1.0)


class OrganizeEvidenceMessage(BaseModel):
    message_id: str
    source: MessageSource
    sender: str
    group_name: str | None = None
    message_time: datetime
    raw_content: str
    category: MessageCategory
    confidence: float
    reason: str
    status: str


class OrganizeClassificationCluster(BaseModel):
    category: MessageCategory
    label: str
    count: int
    average_confidence: float
    low_confidence_count: int
    latest_time: datetime
    evidence: list[OrganizeEvidenceMessage]


class OrganizeClassificationSummary(BaseModel):
    classified_count: int
    total_count: int
    cluster_count: int
    low_confidence_count: int
    noise_count: int
    hidden_count: int
    average_confidence: float


class OrganizeClassificationPage(BaseModel):
    summary: OrganizeClassificationSummary
    clusters: list[OrganizeClassificationCluster]


def list_classification_clusters(
    conn: sqlite3.Connection,
    filters: OrganizeClassificationFilters,
) -> OrganizeClassificationPage:
    """读取离线分类结果，按 category 聚合并附带少量可回溯证据。"""

    base_where, base_params = _base_conditions(filters)
    visible_where, visible_params = _visible_conditions(base_where, base_params, filters.low_confidence_threshold)
    summary = _classification_summary(conn, base_where, base_params, filters.low_confidence_threshold)
    rows = _classification_cluster_rows(conn, visible_where, visible_params, filters.low_confidence_threshold)
    clusters = [
        OrganizeClassificationCluster(
            category=row["display_category"],
            label=CATEGORY_LABELS.get(row["display_category"], row["display_category"]),
            count=row["count"],
            average_confidence=round(float(row["average_confidence"] or 0), 4),
            low_confidence_count=row["low_confidence_count"],
            latest_time=datetime.fromisoformat(row["latest_time"]),
            evidence=_classification_evidence(conn, filters, row["display_category"], visible_where, visible_params),
        )
        for row in rows
    ]
    return OrganizeClassificationPage(summary=summary, clusters=clusters)


def _base_conditions(filters: OrganizeClassificationFilters) -> tuple[list[str], list[object]]:
    where: list[str] = []
    params: list[object] = []
    if filters.source:
        where.append("m.source = ?")
        params.append(filters.source)
    if filters.category:
        if filters.category == "research":
            where.append("c.category IN (?, ?)")
            params.extend(["research", "tool_ad"])
        else:
            where.append("c.category = ?")
            params.append(filters.category)
    if filters.start_time:
        where.append("m.message_time >= ?")
        params.append(filters.start_time.isoformat())
    if filters.end_time:
        where.append("m.message_time <= ?")
        params.append(filters.end_time.isoformat())
    if filters.keyword:
        keyword = f"%{filters.keyword.strip()}%"
        where.append(
            f"""
            (
                m.raw_content LIKE ?
                OR m.sender LIKE ?
                OR COALESCE(m.group_name, '') LIKE ?
                OR c.reason LIKE ?
                OR {_DISPLAY_CATEGORY_SQL} LIKE ?
            )
            """
        )
        params.extend([keyword, keyword, keyword, keyword, keyword])
    return where, params


def _visible_conditions(
    base_where: list[str],
    base_params: list[object],
    low_confidence_threshold: float,
) -> tuple[list[str], list[object]]:
    where = list(base_where)
    params = list(base_params)
    where.append(
        f"""
        c.status IN ('auto', 'confirmed')
        AND c.confidence >= ?
        AND {_DISPLAY_CATEGORY_SQL} IN {_actionable_category_sql()}
        """
    )
    params.append(low_confidence_threshold)
    return where, params


def _classification_summary(
    conn: sqlite3.Connection,
    where: list[str],
    params: list[object],
    low_confidence_threshold: float,
) -> OrganizeClassificationSummary:
    visible_sql = (
        f"c.status IN ('auto', 'confirmed') "
        f"AND c.confidence >= ? "
        f"AND {_DISPLAY_CATEGORY_SQL} IN {_actionable_category_sql()}"
    )
    review_sql = (
        f"{_DISPLAY_CATEGORY_SQL} != 'chat' "
        "AND c.status != 'ignored' "
        f"AND (c.status = 'needs_review' OR c.confidence < ? OR {_DISPLAY_CATEGORY_SQL} = 'unknown')"
    )
    noise_sql = f"c.status = 'ignored' OR {_DISPLAY_CATEGORY_SQL} = 'chat'"
    sql = [
        f"""
        WITH scoped AS (
            SELECT
                c.confidence,
                {_DISPLAY_CATEGORY_SQL} AS display_category,
                CASE WHEN {visible_sql} THEN 1 ELSE 0 END AS is_visible,
                CASE WHEN {review_sql} THEN 1 ELSE 0 END AS is_review,
                CASE WHEN {noise_sql} THEN 1 ELSE 0 END AS is_noise
            FROM message_classifications c
            JOIN messages m ON m.message_id = c.message_id
        """
    ]
    query_params: list[object] = [low_confidence_threshold, low_confidence_threshold, *params]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append(
        """
        )
        SELECT
            COUNT(*) AS classified_count,
            SUM(is_visible) AS total_count,
            COUNT(DISTINCT CASE WHEN is_visible = 1 THEN display_category END) AS cluster_count,
            AVG(CASE WHEN is_visible = 1 THEN confidence ELSE NULL END) AS average_confidence,
            SUM(is_review) AS low_confidence_count,
            SUM(is_noise) AS noise_count
        FROM scoped
        """
    )
    row = conn.execute(" ".join(sql), query_params).fetchone()
    classified_count = row["classified_count"] or 0
    total_count = row["total_count"] or 0
    return OrganizeClassificationSummary(
        classified_count=classified_count,
        total_count=total_count,
        cluster_count=row["cluster_count"] or 0,
        low_confidence_count=row["low_confidence_count"] or 0,
        noise_count=row["noise_count"] or 0,
        hidden_count=max(classified_count - total_count, 0),
        average_confidence=round(float(row["average_confidence"] or 0), 4),
    )


def _classification_cluster_rows(
    conn: sqlite3.Connection,
    where: list[str],
    params: list[object],
    low_confidence_threshold: float,
) -> list[sqlite3.Row]:
    sql = [
        f"""
        SELECT
            {_DISPLAY_CATEGORY_SQL} AS display_category,
            COUNT(*) AS count,
            AVG(c.confidence) AS average_confidence,
            SUM(CASE WHEN c.status = 'needs_review' OR c.confidence < ? THEN 1 ELSE 0 END) AS low_confidence_count,
            MAX(m.message_time) AS latest_time
        FROM message_classifications c
        JOIN messages m ON m.message_id = c.message_id
        """
    ]
    query_params: list[object] = [low_confidence_threshold, *params]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append(f"GROUP BY display_category ORDER BY {_category_order_sql()}, count DESC, latest_time DESC")
    return conn.execute(" ".join(sql), query_params).fetchall()


def _category_order_sql() -> str:
    whens = " ".join(f"WHEN '{category}' THEN {index}" for index, category in enumerate(_CATEGORY_ORDER, start=1))
    return f"CASE display_category {whens} ELSE 99 END"


def _actionable_category_sql() -> str:
    categories = ", ".join(f"'{category}'" for category in _ACTIONABLE_DISPLAY_CATEGORIES)
    return f"({categories})"


def _classification_evidence(
    conn: sqlite3.Connection,
    filters: OrganizeClassificationFilters,
    category: MessageCategory,
    base_where: list[str],
    base_params: list[object],
) -> list[OrganizeEvidenceMessage]:
    where = list(base_where)
    params = list(base_params)
    if not filters.category:
        if category == "research":
            where.append("c.category IN (?, ?)")
            params.extend(["research", "tool_ad"])
        else:
            where.append("c.category = ?")
            params.append(category)
    sql = [
        """
        SELECT
            m.message_id, m.source, m.sender, m.group_name, m.message_time, m.raw_content,
            c.category, c.confidence, c.reason, c.status
        FROM message_classifications c
        JOIN messages m ON m.message_id = c.message_id
        """
    ]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY m.message_time DESC, m.message_id DESC LIMIT ?")
    params.append(filters.evidence_limit)
    rows = conn.execute(" ".join(sql), params).fetchall()
    return [_row_to_evidence(row) for row in rows]


def _row_to_evidence(row: sqlite3.Row) -> OrganizeEvidenceMessage:
    return OrganizeEvidenceMessage(
        message_id=row["message_id"],
        source=row["source"],
        sender=row["sender"],
        group_name=row["group_name"],
        message_time=datetime.fromisoformat(row["message_time"]),
        raw_content=row["raw_content"],
        category="research" if row["category"] == "tool_ad" else row["category"],
        confidence=row["confidence"],
        reason=row["reason"],
        status=row["status"],
    )
