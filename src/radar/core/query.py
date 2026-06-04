from __future__ import annotations

import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.models import MessageSource, RawMessage


class MessageFilters(BaseModel):
    """消息查询条件；CLI 和 Web API 共用同一套入参模型。"""

    source: MessageSource | None = None
    group_name: str | None = None
    sender: str | None = None
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
    """消息里的会话名聚合结果，先复用 group_name 字段给前端候选。"""

    group_name: str
    message_count: int
    first_seen_at: datetime
    last_seen_at: datetime


def list_messages(conn: sqlite3.Connection, filters: MessageFilters) -> MessagePage:
    """按时间倒序分页查询消息，默认不允许一次返回全量。"""

    if not filters.keyword:
        return _list_messages_by_time(conn, filters)
    return _list_messages_with_keyword(conn, filters)


def _list_messages_by_time(conn: sqlite3.Connection, filters: MessageFilters) -> MessagePage:
    """无关键词首屏路径：按时间索引取候选，再做页内去重。"""

    base_where, base_params = _base_message_conditions(filters, include_cursor=False)
    cursor_time = filters.cursor_time
    cursor_id = filters.cursor_id
    batch_limit = max(filters.limit * 4, 100)
    items: list[RawMessage] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    while len(items) <= filters.limit:
        where = list(base_where)
        params = list(base_params)
        if cursor_time and cursor_id:
            # 时间相同时用 message_id 继续排序，保证翻页稳定且不重复。
            where.append("(m.message_time, m.message_id) < (?, ?)")
            params.extend([cursor_time.isoformat(), cursor_id])

        sql = ["SELECT m.* FROM messages m"]
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY m.message_time DESC, m.message_id DESC LIMIT ?")
        params.append(batch_limit)

        rows = conn.execute(" ".join(sql), params).fetchall()
        if not rows:
            break

        for row in rows:
            fingerprint = _row_fingerprint(row)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(_row_to_message(row))
            if len(items) > filters.limit:
                break

        if len(items) > filters.limit or len(rows) < batch_limit:
            break

        last_row = rows[-1]
        cursor_time = datetime.fromisoformat(last_row["message_time"])
        cursor_id = last_row["message_id"]

    has_more = len(items) > filters.limit
    page_items = items[: filters.limit]
    if not has_more or not page_items:
        return MessagePage(items=page_items)

    last = page_items[-1]
    return MessagePage(items=page_items, next_cursor_time=last.message_time, next_cursor_id=last.message_id)


def _list_messages_with_keyword(conn: sqlite3.Connection, filters: MessageFilters) -> MessagePage:
    """关键词路径仍走数据库内去重，保证搜索语义稳定。"""

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

    keyword = filters.keyword.strip()
    if len(keyword) >= 3:
        sql.append("JOIN messages_fts fts ON fts.message_id = m.message_id")
        where.append("messages_fts MATCH ?")
        params.append(keyword)
    else:
        # FTS5 trigram 对 1-2 字中文词不稳定，短词用 SQL LIKE 兜底，但仍在数据库内执行。
        where.append("(m.raw_content LIKE ? OR m.sender LIKE ? OR m.group_name LIKE ?)")
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword])

    base_where, base_params = _base_message_conditions(filters, include_cursor=True)
    where.extend(base_where)
    params.extend(base_params)

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


def _base_message_conditions(filters: MessageFilters, *, include_cursor: bool) -> tuple[list[str], list[object]]:
    where: list[str] = []
    params: list[object] = []
    if filters.source:
        where.append("m.source = ?")
        params.append(filters.source)
    if filters.group_name:
        if filters.source == "个人消息":
            where.append("m.sender = ?")
            params.append(filters.group_name)
        elif filters.source == "个人群":
            where.append("m.group_name = ?")
            params.append(filters.group_name)
        else:
            where.append(
                "((m.source = '个人群' AND m.group_name = ?) OR (m.source = '个人消息' AND m.sender = ?))"
            )
            params.extend([filters.group_name, filters.group_name])
    if filters.sender:
        where.append("m.sender = ?")
        params.append(filters.sender)
    if filters.start_time:
        where.append("m.message_time >= ?")
        params.append(filters.start_time.isoformat())
    if filters.end_time:
        where.append("m.message_time <= ?")
        params.append(filters.end_time.isoformat())
    if include_cursor and filters.cursor_time and filters.cursor_id:
        # 时间相同时用 message_id 继续排序，保证翻页稳定且不重复。
        where.append("(m.message_time, m.message_id) < (?, ?)")
        params.extend([filters.cursor_time.isoformat(), filters.cursor_id])
    return where, params


def list_message_groups(
    conn: sqlite3.Connection,
    *,
    source: MessageSource | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> list[MessageGroupSummary]:
    """按来源聚合群名或联系人名，供会话筛选下拉复用。"""

    name_expr = _message_group_name_expr(source)

    sql = [
        f"""
        SELECT
            {name_expr} AS group_name,
            COUNT(*) AS message_count,
            MIN(message_time) AS first_seen_at,
            MAX(message_time) AS last_seen_at
        FROM messages
        WHERE {name_expr} <> ''
        """
    ]
    params: list[object] = []
    if source:
        sql.append("AND source = ?")
        params.append(source)
    if keyword:
        sql.append(f"AND {name_expr} LIKE ?")
        params.append(f"%{keyword}%")
    sql.append(f"GROUP BY {name_expr} ORDER BY message_count DESC, last_seen_at DESC LIMIT ?")
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


def _message_group_name_expr(source: MessageSource | None) -> str:
    if source == "个人群":
        return "COALESCE(group_name, '')"
    if source == "个人消息":
        return "sender"
    return """
    CASE
        WHEN source = '个人群' THEN COALESCE(group_name, '')
        ELSE sender
    END
    """


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


def _row_fingerprint(row: sqlite3.Row) -> tuple[str, str, str, str, str]:
    return (
        row["source"],
        row["sender"],
        row["message_time"],
        row["raw_content"],
        row["group_name"] or "",
    )
