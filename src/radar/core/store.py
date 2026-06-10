from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from radar.core.db import migrate_message_db
from radar.core.models import (
    ClassificationRetryMode,
    MessageCategory,
    MessageClassification,
    MessageSource,
    RawMessage,
)


def connect(database_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接；调用方负责关闭连接。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """初始化表和索引；FTS5 trigram 支持中文片段搜索，避免 Python 扫全库。"""

    migrate_message_db(conn)


def upsert_messages(conn: sqlite3.Connection, messages: list[RawMessage]) -> int:
    """按 message_id 去重写入，返回本次新增数量。"""

    inserted = 0
    for message in messages:
        if _message_fingerprint_exists(conn, message):
            continue
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO messages (
                message_id, source, sender, message_time, raw_content,
                group_name, fetch_time, fetch_window
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.message_id,
                message.source,
                message.sender,
                message.message_time.isoformat(),
                message.raw_content,
                message.group_name,
                message.fetch_time.isoformat(),
                message.fetch_window,
            ),
        )
        if cursor.rowcount == 1:
            inserted += 1
            conn.execute(
                """
                INSERT INTO messages_fts (message_id, raw_content, sender, group_name)
                VALUES (?, ?, ?, ?)
                """,
                (message.message_id, message.raw_content, message.sender, message.group_name or ""),
            )
    conn.commit()
    return inserted


def upsert_message_classifications(
    conn: sqlite3.Connection,
    classifications: list[MessageClassification],
) -> int:
    """写入消息分类派生结果，返回本次新增 message_id 数量。"""

    if not classifications:
        return 0

    message_ids = [item.message_id for item in classifications]
    existing = classified_message_ids(conn, message_ids=message_ids)
    for item in classifications:
        conn.execute(
            """
            INSERT INTO message_classifications (
                message_id, category, confidence, reason, status, classifier_type,
                llm_provider, model, prompt_version, classifier_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                category = excluded.category,
                confidence = excluded.confidence,
                reason = excluded.reason,
                status = excluded.status,
                classifier_type = excluded.classifier_type,
                llm_provider = excluded.llm_provider,
                model = excluded.model,
                prompt_version = excluded.prompt_version,
                classifier_version = excluded.classifier_version,
                updated_at = excluded.updated_at
            """,
            (
                item.message_id,
                item.category,
                item.confidence,
                item.reason,
                item.status,
                item.classifier_type,
                item.llm_provider,
                item.model,
                item.prompt_version,
                item.classifier_version,
                item.created_at.isoformat(),
                item.updated_at.isoformat(),
            ),
        )
    conn.commit()
    return len(set(message_ids) - existing)


def list_messages_for_classification(
    conn: sqlite3.Connection,
    *,
    source: MessageSource | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    end_inclusive: bool = True,
    cursor_time: str | None = None,
    cursor_id: str | None = None,
    limit: int = 500,
    force: bool = False,
    retry: ClassificationRetryMode | None = None,
    low_confidence_threshold: float = 0.65,
) -> list[RawMessage]:
    """读取待分类消息；默认跳过已存在分类结果的 message_id。"""

    where: list[str] = []
    params: list[object] = []
    joins = ""
    if force:
        pass
    elif retry:
        joins = "JOIN message_classifications c ON c.message_id = m.message_id"
        _append_classification_retry_condition(
            where,
            params,
            retry=retry,
            low_confidence_threshold=low_confidence_threshold,
        )
    else:
        joins = "LEFT JOIN message_classifications c ON c.message_id = m.message_id"
        where.append("c.message_id IS NULL")
    if source:
        where.append("m.source = ?")
        params.append(source)
    if start_time:
        where.append("m.message_time >= ?")
        params.append(start_time)
    if end_time:
        operator = "<=" if end_inclusive else "<"
        where.append(f"m.message_time {operator} ?")
        params.append(end_time)
    if cursor_time and cursor_id:
        where.append("(m.message_time, m.message_id) < (?, ?)")
        params.extend([cursor_time, cursor_id])

    sql = [
        "SELECT m.* FROM messages m",
        joins,
    ]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY m.message_time DESC, m.message_id DESC LIMIT ?")
    params.append(limit)
    rows = conn.execute(" ".join(part for part in sql if part), params).fetchall()
    return [_row_to_message(row) for row in rows]


def _append_classification_retry_condition(
    where: list[str],
    params: list[object],
    *,
    retry: ClassificationRetryMode,
    low_confidence_threshold: float,
) -> None:
    if retry == "needs_review":
        where.append("c.status = ?")
        params.append("needs_review")
    elif retry == "unknown":
        where.append("c.category = ? AND c.status != ?")
        params.extend(["unknown", "confirmed"])
    elif retry == "low_confidence":
        where.append("c.confidence < ? AND c.status != ?")
        params.extend([low_confidence_threshold, "confirmed"])


def classified_message_ids(
    conn: sqlite3.Connection,
    *,
    message_ids: list[str] | None = None,
) -> set[str]:
    """查询已有分类结果，供增量分类跳过已处理消息。"""

    if message_ids == []:
        return set()
    if message_ids is None:
        rows = conn.execute("SELECT message_id FROM message_classifications").fetchall()
    else:
        placeholders = ", ".join("?" for _ in message_ids)
        rows = conn.execute(
            f"SELECT message_id FROM message_classifications WHERE message_id IN ({placeholders})",
            message_ids,
        ).fetchall()
    return {str(row["message_id"]) for row in rows}


def _row_to_message(row: sqlite3.Row) -> RawMessage:
    return RawMessage(
        message_id=row["message_id"],
        source=row["source"],
        sender=row["sender"],
        message_time=_datetime_from_iso(row["message_time"]),
        raw_content=row["raw_content"],
        group_name=row["group_name"],
        fetch_time=_datetime_from_iso(row["fetch_time"]),
        fetch_window=row["fetch_window"],
    )


def _datetime_from_iso(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _message_fingerprint_exists(conn: sqlite3.Connection, message: RawMessage) -> bool:
    """兼容历史迁移和 API 重复返回：同源、同人、同时间、同内容视为同一条。"""

    row = conn.execute(
        """
        SELECT 1 FROM messages
        WHERE source = ?
          AND sender = ?
          AND message_time = ?
          AND raw_content = ?
          AND COALESCE(group_name, '') = ?
        LIMIT 1
        """,
        (
            message.source,
            message.sender,
            message.message_time.isoformat(),
            message.raw_content,
            message.group_name or "",
        ),
    ).fetchone()
    return row is not None


def fetch_window_exists(
    conn: sqlite3.Connection,
    *,
    source: str,
    start_time: str,
    end_time: str,
) -> bool:
    """检查同一 source + 时间窗是否已完成写入，避免重复拉取。"""

    row = conn.execute(
        """
        SELECT 1 FROM fetch_windows
        WHERE source = ? AND start_time = ? AND end_time = ?
        """,
        (source, start_time, end_time),
    ).fetchone()
    return row is not None


def fetch_window_covered(
    conn: sqlite3.Connection,
    *,
    source: str,
    start_time: str,
    end_time: str,
) -> bool:
    """检查目标窗口是否已被更大或相同窗口覆盖，避免切片后重复拉取。"""

    row = conn.execute(
        """
        SELECT 1 FROM fetch_windows
        WHERE source = ? AND start_time <= ? AND end_time >= ?
        LIMIT 1
        """,
        (source, start_time, end_time),
    ).fetchone()
    return row is not None


def record_fetch_window(
    conn: sqlite3.Connection,
    *,
    source: str,
    start_time: str,
    end_time: str,
    fetched_at: str,
    raw_count: int,
    stored_count: int,
    filtered_count: int,
) -> None:
    """记录已处理窗口；窗口存在性由该表负责，不靠文件名推断。"""

    conn.execute(
        """
        INSERT OR REPLACE INTO fetch_windows (
            source, start_time, end_time, fetched_at, raw_count, stored_count, filtered_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source, start_time, end_time, fetched_at, raw_count, stored_count, filtered_count),
    )
    conn.commit()
