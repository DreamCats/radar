from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from radar.core.storage.db import SQLITE_TIMEOUT_SECONDS, configure_sqlite_connection, migrate_message_db
from radar.core.models import (
    MessageSource,
    RawMessage,
)


def connect(database_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接；调用方负责关闭连接。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
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
