from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence

from radar.core.storage.market_migrations import MARKET_MIGRATIONS
from radar.core.storage.message_migrations import MESSAGE_MIGRATIONS

Migration = tuple[str, str]
_MIGRATION_LOCK = threading.Lock()


def migrate_message_db(conn: sqlite3.Connection) -> None:
    """迁移消息库；老库会补 schema_migrations 并按版本补表/索引。"""

    migrate(conn, MESSAGE_MIGRATIONS)


def migrate_market_db(conn: sqlite3.Connection) -> None:
    """迁移行情库；market.sqlite3 独立记录自己的 schema 版本。"""

    migrate(conn, MARKET_MIGRATIONS)


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> None:
    with _MIGRATION_LOCK:
        conn.execute("PRAGMA busy_timeout = 5000")
        _ensure_migration_table(conn)
        applied = applied_migrations(conn)
        for version, sql in migrations:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
            conn.commit()
            applied.add(version)


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
