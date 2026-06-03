from __future__ import annotations

import sqlite3
from pathlib import Path

from radar.core.models import RawMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    sender TEXT NOT NULL,
    message_time TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    group_name TEXT,
    fetch_time TEXT NOT NULL,
    fetch_window TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_windows (
    source TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_count INTEGER NOT NULL,
    stored_count INTEGER NOT NULL,
    filtered_count INTEGER NOT NULL,
    PRIMARY KEY (source, start_time, end_time)
);

CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(message_time DESC, message_id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_name);
CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    message_id UNINDEXED,
    raw_content,
    sender,
    group_name,
    tokenize = 'trigram'
);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接；调用方负责关闭连接。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """初始化表和索引；FTS5 trigram 支持中文片段搜索，避免 Python 扫全库。"""

    conn.executescript(SCHEMA)
    conn.commit()


def upsert_messages(conn: sqlite3.Connection, messages: list[RawMessage]) -> int:
    """按 message_id 去重写入，返回本次新增数量。"""

    inserted = 0
    for message in messages:
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
