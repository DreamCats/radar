from __future__ import annotations

import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.models import MessageSource


class ConversationFilters(BaseModel):
    """微信会话列表筛选；分页边界是会话最近一条消息。"""

    source: MessageSource | None = None
    group_name: str | None = None
    keyword: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    cursor_time: datetime | None = None
    cursor_key: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class ConversationSummary(BaseModel):
    key: str
    title: str
    source: MessageSource
    latest_sender: str
    latest_time: datetime
    latest_content: str
    latest_message_id: str
    message_count: int


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    next_cursor_time: datetime | None = None
    next_cursor_key: str | None = None


def list_conversations(conn: sqlite3.Connection, filters: ConversationFilters) -> ConversationPage:
    """按微信会话维度分页：每个群/联系人只取最近一条消息。"""

    if not filters.keyword:
        return _list_conversations_by_identity(conn, filters)

    sql = [
        "WITH filtered AS (",
        """
        SELECT m.*
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

    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.extend(
        [
            """
            ),
            keyed AS (
                SELECT *,
                       CASE
                           WHEN source = '个人群' THEN COALESCE(group_name, '')
                           ELSE sender
                       END AS conversation_title
                FROM filtered
                WHERE CASE
                          WHEN source = '个人群' THEN COALESCE(group_name, '')
                          ELSE sender
                      END <> ''
            ),
            latest AS (
                SELECT
                       source,
                       conversation_title,
                       source || ':' || conversation_title AS conversation_key,
                       COUNT(*) AS conversation_count,
                       MAX(message_time || char(31) || message_id) AS latest_key
                FROM keyed
                GROUP BY source, conversation_title
            ),
            page AS (
                SELECT
                    latest.conversation_key,
                    latest.conversation_title,
                    latest.source,
                    m.sender,
                    m.message_time,
                    m.raw_content,
                    m.message_id,
                    latest.conversation_count
                FROM latest
                JOIN messages m
                  ON m.message_id = substr(latest.latest_key, instr(latest.latest_key, char(31)) + 1)
            )
            SELECT
                conversation_key,
                conversation_title,
                source,
                sender,
                message_time,
                raw_content,
                message_id,
                conversation_count
            FROM page
            WHERE 1 = 1
            """
        ]
    )
    if filters.cursor_time and filters.cursor_key:
        sql.append("AND (message_time, conversation_key) < (?, ?)")
        params.extend([filters.cursor_time.isoformat(), filters.cursor_key])
    sql.append("ORDER BY message_time DESC, conversation_key DESC LIMIT ?")
    params.append(filters.limit + 1)

    rows = conn.execute(" ".join(sql), params).fetchall()
    return _conversation_page_from_rows(rows, filters.limit)


def _list_conversations_by_identity(conn: sqlite3.Connection, filters: ConversationFilters) -> ConversationPage:
    """无关键词首屏路径：分别按群名/联系人聚合，避免 CASE 分组拖慢会话列表。"""

    selects: list[str] = []
    params: list[object] = []

    if filters.source in (None, "个人群"):
        where = ["source = '个人群'", "group_name IS NOT NULL", "group_name <> ''"]
        if filters.group_name:
            where.append("group_name = ?")
            params.append(filters.group_name)
        if filters.start_time:
            where.append("message_time >= ?")
            params.append(filters.start_time.isoformat())
        if filters.end_time:
            where.append("message_time <= ?")
            params.append(filters.end_time.isoformat())
        selects.append(
            f"""
            SELECT source,
                   group_name AS conversation_title,
                   source || ':' || group_name AS conversation_key,
                   COUNT(*) AS conversation_count,
                   MAX(message_time || char(31) || message_id) AS latest_key
            FROM messages
            WHERE {" AND ".join(where)}
            GROUP BY source, group_name
            """
        )

    if filters.source in (None, "个人消息") and not filters.group_name:
        where = ["source = '个人消息'", "sender <> ''"]
        if filters.start_time:
            where.append("message_time >= ?")
            params.append(filters.start_time.isoformat())
        if filters.end_time:
            where.append("message_time <= ?")
            params.append(filters.end_time.isoformat())
        selects.append(
            f"""
            SELECT source,
                   sender AS conversation_title,
                   source || ':' || sender AS conversation_key,
                   COUNT(*) AS conversation_count,
                   MAX(message_time || char(31) || message_id) AS latest_key
            FROM messages
            WHERE {" AND ".join(where)}
            GROUP BY source, sender
            """
        )

    if not selects:
        return ConversationPage(items=[])

    sql = [
        "WITH latest AS (",
        " UNION ALL ".join(selects),
        """
        ),
        page AS (
            SELECT
                latest.conversation_key,
                latest.conversation_title,
                latest.source,
                m.sender,
                m.message_time,
                m.raw_content,
                m.message_id,
                latest.conversation_count
            FROM latest
            JOIN messages m
              ON m.message_id = substr(latest.latest_key, instr(latest.latest_key, char(31)) + 1)
        )
        SELECT
            conversation_key,
            conversation_title,
            source,
            sender,
            message_time,
            raw_content,
            message_id,
            conversation_count
        FROM page
        WHERE 1 = 1
        """,
    ]
    if filters.cursor_time and filters.cursor_key:
        sql.append("AND (message_time, conversation_key) < (?, ?)")
        params.extend([filters.cursor_time.isoformat(), filters.cursor_key])
    sql.append("ORDER BY message_time DESC, conversation_key DESC LIMIT ?")
    params.append(filters.limit + 1)

    rows = conn.execute(" ".join(sql), params).fetchall()
    return _conversation_page_from_rows(rows, filters.limit)


def _conversation_page_from_rows(rows: list[sqlite3.Row], limit: int) -> ConversationPage:
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = [
        ConversationSummary(
            key=row["conversation_key"],
            title=row["conversation_title"],
            source=row["source"],
            latest_sender=row["sender"],
            latest_time=datetime.fromisoformat(row["message_time"]),
            latest_content=row["raw_content"],
            latest_message_id=row["message_id"],
            message_count=row["conversation_count"],
        )
        for row in page_rows
    ]
    if not has_more or not items:
        return ConversationPage(items=items)

    last = items[-1]
    return ConversationPage(items=items, next_cursor_time=last.latest_time, next_cursor_key=last.key)
