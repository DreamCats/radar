from __future__ import annotations

import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.models import MessageSource, RawMessage


class MessageFilters(BaseModel):
    """消息查询条件；CLI 和 Web API 共用同一套入参模型。"""

    source: MessageSource | None = None
    group_name: str | None = None
    keyword: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    cursor_time: datetime | None = None
    cursor_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class MessagePage(BaseModel):
    items: list[RawMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None


class MessageGroupSummary(BaseModel):
    """消息里的群名聚合结果，先不引入复杂群维表。"""

    group_name: str
    message_count: int
    first_seen_at: datetime
    last_seen_at: datetime


def list_messages(conn: sqlite3.Connection, filters: MessageFilters) -> MessagePage:
    """按时间倒序分页查询消息，默认不允许一次返回全量。"""

    sql = [
        "SELECT * FROM (",
        """
        SELECT m.*,
               ROW_NUMBER() OVER (
                   PARTITION BY m.source, m.sender, m.message_time, m.raw_content, COALESCE(m.group_name, '')
                   ORDER BY m.message_id
               ) AS dedupe_rank
        FROM messages m
        """,
    ]
    where: list[str] = []
    params: list[object] = []

    keyword = filters.keyword.strip() if filters.keyword else None
    if keyword and len(keyword) >= 3:
        sql.append("JOIN messages_fts fts ON fts.message_id = m.message_id")
        where.append("messages_fts MATCH ?")
        params.append(keyword)
    elif keyword:
        # FTS5 trigram 对 1-2 字中文词不稳定，短词用 SQL LIKE 兜底，但仍在数据库内执行。
        where.append("(m.raw_content LIKE ? OR m.sender LIKE ? OR m.group_name LIKE ?)")
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword])
    if filters.source:
        where.append("m.source = ?")
        params.append(filters.source)
    if filters.group_name:
        where.append("m.group_name = ?")
        params.append(filters.group_name)
    if filters.start_time:
        where.append("m.message_time >= ?")
        params.append(filters.start_time.isoformat())
    if filters.end_time:
        where.append("m.message_time <= ?")
        params.append(filters.end_time.isoformat())
    if filters.cursor_time and filters.cursor_id:
        # 时间相同时用 message_id 继续排序，保证翻页稳定且不重复。
        where.append("(m.message_time, m.message_id) < (?, ?)")
        params.extend([filters.cursor_time.isoformat(), filters.cursor_id])

    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append(") WHERE dedupe_rank = 1")
    sql.append("ORDER BY message_time DESC, message_id DESC LIMIT ?")
    params.append(filters.limit + 1)

    rows = conn.execute(" ".join(sql), params).fetchall()
    has_more = len(rows) > filters.limit
    page_rows = rows[: filters.limit]
    items = [_row_to_message(row) for row in page_rows]
    if not has_more or not items:
        return MessagePage(items=items)

    last = items[-1]
    return MessagePage(items=items, next_cursor_time=last.message_time, next_cursor_id=last.message_id)


def list_message_groups(
    conn: sqlite3.Connection,
    *,
    source: MessageSource | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> list[MessageGroupSummary]:
    """从消息表聚合群名，供筛选下拉和后续群管理能力复用。"""

    sql = [
        """
        SELECT
            group_name,
            COUNT(*) AS message_count,
            MIN(message_time) AS first_seen_at,
            MAX(message_time) AS last_seen_at
        FROM messages
        WHERE group_name IS NOT NULL AND group_name <> ''
        """
    ]
    params: list[object] = []
    if source:
        sql.append("AND source = ?")
        params.append(source)
    if keyword:
        sql.append("AND group_name LIKE ?")
        params.append(f"%{keyword}%")
    sql.append("GROUP BY group_name ORDER BY message_count DESC, last_seen_at DESC LIMIT ?")
    params.append(limit)

    rows = conn.execute(" ".join(sql), params).fetchall()
    return [
        MessageGroupSummary(
            group_name=row["group_name"],
            message_count=row["message_count"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        )
        for row in rows
    ]


def _row_to_message(row: sqlite3.Row) -> RawMessage:
    return RawMessage(
        message_id=row["message_id"],
        source=row["source"],
        sender=row["sender"],
        message_time=datetime.fromisoformat(row["message_time"]),
        raw_content=row["raw_content"],
        group_name=row["group_name"],
        fetch_time=datetime.fromisoformat(row["fetch_time"]),
        fetch_window=row["fetch_window"],
    )
