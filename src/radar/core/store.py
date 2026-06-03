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
