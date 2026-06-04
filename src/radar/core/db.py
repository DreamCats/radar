from __future__ import annotations

import sqlite3
from collections.abc import Sequence

Migration = tuple[str, str]


MESSAGE_MIGRATIONS: list[Migration] = [
    (
        "001_init_messages",
        """
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

        CREATE INDEX IF NOT EXISTS idx_messages_time
            ON messages(message_time DESC, message_id DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_name);
        CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            message_id UNINDEXED,
            raw_content,
            sender,
            group_name,
            tokenize = 'trigram'
        );
        """,
    ),
    (
        "002_init_runs",
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            target TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            raw_count INTEGER NOT NULL DEFAULT 0,
            stored_count INTEGER NOT NULL DEFAULT 0,
            filtered_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_runs_kind_started
            ON runs(kind, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_status_started
            ON runs(status, started_at DESC);
        """,
    ),
    (
        "003_message_fingerprint_index",
        """
        CREATE INDEX IF NOT EXISTS idx_messages_fingerprint_lookup
            ON messages(source, sender, message_time, group_name);
        """,
    ),
    (
        "004_message_conversation_indexes",
        """
        CREATE INDEX IF NOT EXISTS idx_messages_group_conversation
            ON messages(source, group_name, message_time DESC, message_id DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_sender_conversation
            ON messages(source, sender, message_time DESC, message_id DESC);
        """,
    ),
    (
        "005_message_source_time_index",
        """
        CREATE INDEX IF NOT EXISTS idx_messages_source_time
            ON messages(source, message_time DESC, message_id DESC);
        """,
    ),
    (
        "006_message_classifications",
        """
        CREATE TABLE IF NOT EXISTS message_classifications (
            message_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            classifier_type TEXT NOT NULL,
            llm_provider TEXT,
            model TEXT,
            prompt_version TEXT,
            classifier_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_message_classifications_category
            ON message_classifications(category, status);
        CREATE INDEX IF NOT EXISTS idx_message_classifications_status
            ON message_classifications(status, updated_at DESC);
        """,
    ),
]

MARKET_MIGRATIONS: list[Migration] = [
    (
        "001_init_market",
        """
        CREATE TABLE IF NOT EXISTS tushare_cache (
            key        TEXT PRIMARY KEY,
            api_name   TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            data       TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tushare_cache_api
            ON tushare_cache(api_name);

        CREATE TABLE IF NOT EXISTS tushare_history (
            api_name TEXT NOT NULL,
            ts_code  TEXT NOT NULL DEFAULT '',
            date_key TEXT NOT NULL,
            data     TEXT NOT NULL,
            PRIMARY KEY (api_name, ts_code, date_key)
        );

        CREATE INDEX IF NOT EXISTS idx_tushare_history_lookup
            ON tushare_history(api_name, ts_code, date_key);
        """,
    ),
]


def migrate_message_db(conn: sqlite3.Connection) -> None:
    """迁移消息库；老库会补 schema_migrations 并按版本补表/索引。"""

    migrate(conn, MESSAGE_MIGRATIONS)


def migrate_market_db(conn: sqlite3.Connection) -> None:
    """迁移行情库；market.sqlite3 独立记录自己的 schema 版本。"""

    migrate(conn, MARKET_MIGRATIONS)


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> None:
    _ensure_migration_table(conn)
    applied = applied_migrations(conn)
    for version, sql in migrations:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    _ensure_migration_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row[0]) for row in rows}


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
