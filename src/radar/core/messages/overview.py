from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from radar.core.models import MessageSource


class MessageOverviewSummary(BaseModel):
    """总览页顶部指标；只返回聚合摘要，不返回真实消息内容。"""

    total_count: int
    group_message_count: int
    personal_message_count: int
    group_count: int
    sender_count: int
    first_message_time: datetime | None = None
    latest_message_time: datetime | None = None


class MessageOverviewBucket(BaseModel):
    date: str
    total_count: int
    group_message_count: int
    personal_message_count: int


class MessageOverviewSource(BaseModel):
    source: MessageSource
    count: int


class MessageOverviewGroup(BaseModel):
    group_name: str
    count: int
    last_message_time: datetime


class MessageOverviewHour(BaseModel):
    hour: int
    count: int


class MessageOverview(BaseModel):
    summary: MessageOverviewSummary
    date_buckets: list[MessageOverviewBucket]
    source_breakdown: list[MessageOverviewSource]
    top_groups: list[MessageOverviewGroup]
    hourly_buckets: list[MessageOverviewHour]


def get_message_overview(
    conn: sqlite3.Connection,
    *,
    days: int = 14,
    top_limit: int = 8,
) -> MessageOverview:
    """按数据库聚合总览数据，避免 Web 首屏拉取大量消息再统计。"""

    summary = _summary(conn)
    if summary.latest_message_time is None:
        return MessageOverview(
            summary=summary,
            date_buckets=[],
            source_breakdown=[],
            top_groups=[],
            hourly_buckets=[],
        )

    start_date = summary.latest_message_time.date() - timedelta(days=days - 1)
    return MessageOverview(
        summary=summary,
        date_buckets=_date_buckets(conn, start_date=start_date, days=days),
        source_breakdown=_source_breakdown(conn),
        top_groups=_top_groups(conn, limit=top_limit),
        hourly_buckets=_hourly_buckets(conn),
    )


def _summary(conn: sqlite3.Connection) -> MessageOverviewSummary:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN source = '个人群' THEN 1 ELSE 0 END), 0) AS group_message_count,
            COALESCE(SUM(CASE WHEN source = '个人消息' THEN 1 ELSE 0 END), 0) AS personal_message_count,
            COUNT(DISTINCT CASE WHEN source = '个人群' THEN group_name END) AS group_count,
            COUNT(DISTINCT sender) AS sender_count,
            MIN(message_time) AS first_message_time,
            MAX(message_time) AS latest_message_time
        FROM messages
        """
    ).fetchone()
    return MessageOverviewSummary(
        total_count=row["total_count"],
        group_message_count=row["group_message_count"],
        personal_message_count=row["personal_message_count"],
        group_count=row["group_count"],
        sender_count=row["sender_count"],
        first_message_time=_datetime_or_none(row["first_message_time"]),
        latest_message_time=_datetime_or_none(row["latest_message_time"]),
    )


def _date_buckets(conn: sqlite3.Connection, *, start_date: date, days: int) -> list[MessageOverviewBucket]:
    # 先查库内已有日期，再补齐空日期，避免折线图因为无消息日期断裂。
    start_at = datetime.combine(start_date, time.min).isoformat()
    rows = conn.execute(
        """
        SELECT
            substr(message_time, 1, 10) AS bucket_date,
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN source = '个人群' THEN 1 ELSE 0 END), 0) AS group_message_count,
            COALESCE(SUM(CASE WHEN source = '个人消息' THEN 1 ELSE 0 END), 0) AS personal_message_count
        FROM messages
        WHERE message_time >= ?
        GROUP BY bucket_date
        ORDER BY bucket_date ASC
        """,
        (start_at,),
    ).fetchall()
    by_date = {
        row["bucket_date"]: MessageOverviewBucket(
            date=row["bucket_date"],
            total_count=row["total_count"],
            group_message_count=row["group_message_count"],
            personal_message_count=row["personal_message_count"],
        )
        for row in rows
    }
    return [
        by_date.get(
            current.isoformat(),
            MessageOverviewBucket(
                date=current.isoformat(),
                total_count=0,
                group_message_count=0,
                personal_message_count=0,
            ),
        )
        for current in (start_date + timedelta(days=offset) for offset in range(days))
    ]


def _source_breakdown(conn: sqlite3.Connection) -> list[MessageOverviewSource]:
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM messages
        GROUP BY source
        ORDER BY count DESC
        """
    ).fetchall()
    return [MessageOverviewSource(source=row["source"], count=row["count"]) for row in rows]


def _top_groups(conn: sqlite3.Connection, *, limit: int) -> list[MessageOverviewGroup]:
    rows = conn.execute(
        """
        SELECT
            group_name,
            COUNT(*) AS count,
            MAX(message_time) AS last_message_time
        FROM messages
        WHERE source = '个人群' AND COALESCE(group_name, '') <> ''
        GROUP BY group_name
        ORDER BY count DESC, last_message_time DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        MessageOverviewGroup(
            group_name=row["group_name"],
            count=row["count"],
            last_message_time=datetime.fromisoformat(row["last_message_time"]),
        )
        for row in rows
    ]


def _hourly_buckets(conn: sqlite3.Connection) -> list[MessageOverviewHour]:
    rows = conn.execute(
        """
        SELECT CAST(substr(message_time, 12, 2) AS INTEGER) AS hour, COUNT(*) AS count
        FROM messages
        GROUP BY hour
        ORDER BY hour ASC
        """
    ).fetchall()
    by_hour = {row["hour"]: row["count"] for row in rows}
    return [MessageOverviewHour(hour=hour, count=by_hour.get(hour, 0)) for hour in range(24)]


def _datetime_or_none(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
