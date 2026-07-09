from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence

from radar.core.storage.market_migrations import MARKET_MIGRATIONS
from radar.core.storage.message_migrations import MESSAGE_MIGRATIONS
from radar.core.storage.report_migrations import REPORT_MIGRATIONS
from radar.core.storage.valuation_migrations import VALUATION_MIGRATIONS

Migration = tuple[str, str]
_MIGRATION_LOCK = threading.Lock()
SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30_000


def configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS,
    enable_wal: bool = True,
) -> None:
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    if not enable_wal:
        return
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise


def migrate_message_db(conn: sqlite3.Connection) -> None:
    """迁移消息库；老库会补 schema_migrations 并按版本补表/索引。"""

    migrate(conn, MESSAGE_MIGRATIONS)


def migrate_market_db(conn: sqlite3.Connection) -> None:
    """迁移行情库；market.sqlite3 独立记录自己的 schema 版本。"""

    migrate(conn, MARKET_MIGRATIONS)


def migrate_report_db(conn: sqlite3.Connection) -> None:
    """迁移报告库；报告归档不耦合原始消息库。"""

    migrate(conn, REPORT_MIGRATIONS)


def migrate_valuation_db(conn: sqlite3.Connection) -> None:
    """迁移估值测算库；只保存异步研究结果投影。"""

    migrate(conn, VALUATION_MIGRATIONS)


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> None:
    with _MIGRATION_LOCK:
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
