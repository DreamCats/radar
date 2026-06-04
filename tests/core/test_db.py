from __future__ import annotations

import sqlite3

from radar.core.db import applied_migrations, migrate_market_db, migrate_message_db


def test_message_db_migrations_create_expected_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "radar.sqlite3")
    try:
        migrate_message_db(conn)

        tables = _tables(conn)
        assert {
            "schema_migrations",
            "messages",
            "messages_fts",
            "fetch_windows",
            "runs",
            "message_classifications",
        } <= tables
        assert applied_migrations(conn) == {
            "001_init_messages",
            "002_init_runs",
            "003_message_fingerprint_index",
            "004_message_conversation_indexes",
            "005_message_source_time_index",
            "006_message_classifications",
        }
    finally:
        conn.close()


def test_market_db_migrations_are_independent(tmp_path):
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)

        tables = _tables(conn)
        assert {"schema_migrations", "tushare_cache", "tushare_history"} <= tables
        assert applied_migrations(conn) == {"001_init_market"}
        assert "messages" not in tables
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "radar.sqlite3")
    try:
        migrate_message_db(conn)
        migrate_message_db(conn)

        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 6
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
    ).fetchall()
    return {row[0] for row in rows}
