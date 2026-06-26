from __future__ import annotations

import sqlite3

from radar.core.storage.db import applied_migrations, migrate_market_db, migrate_message_db


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
            "analyst_stock_mentions",
            "analyst_stock_mention_windows",
            "analysts",
            "analyst_aliases",
            "job_schedules",
            "job_schedule_ticks",
        } <= tables
        assert "view_cache" not in tables
        assert "strategy_snapshots" not in tables
        assert "strategy_snapshot_stocks" not in tables
        assert "strategy_snapshot_returns" not in tables
        assert "message_anchors" not in tables
        assert "message_anchor_status" not in tables
        assert "aggregate_refine_results" not in tables
        assert "source_structures" not in tables
        assert "source_signal_snapshots" not in tables
        assert "recommendation_events" not in tables
        assert "recommendation_backtest_windows" not in tables
        assert "message_classifications" not in tables
        assert "stock_message_mentions" not in tables
        assert "stock_lifecycle_candidates" not in tables
        assert "stock_lifecycle_judgements" not in tables
        assert "stock_mention_status" not in tables
        assert "opportunity_lifecycle_digests" not in tables
        assert applied_migrations(conn) == {
            "001_message_schema",
        }
        analyst_columns = _columns(conn, "analyst_stock_mentions")
        assert "category" not in analyst_columns
        assert "classification_confidence" not in analyst_columns
    finally:
        conn.close()


def test_market_db_migrations_are_independent(tmp_path):
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)

        tables = _tables(conn)
        assert {
            "schema_migrations",
            "stocks",
            "tushare_cache",
            "tushare_history",
        } <= tables
        assert "market_anchors" not in tables
        assert "market_anchor_members" not in tables
        assert "market_anchor_current_members" not in tables
        assert "market_anchor_member_spans" not in tables
        assert "theme_nodes" not in tables
        assert "theme_source_links" not in tables
        assert "stock_theme_memberships" not in tables
        assert applied_migrations(conn) == {
            "001_market_schema",
            "002_stock_master",
        }
        assert "messages" not in tables
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "radar.sqlite3")
    try:
        migrate_message_db(conn)
        migrate_message_db(conn)

        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
    ).fetchall()
    return {row[0] for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}
