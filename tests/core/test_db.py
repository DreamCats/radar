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
            "aggregate_refine_results",
            "recommendation_events",
            "recommendation_backtest_windows",
            "analysts",
            "analyst_aliases",
            "view_cache",
            "stock_message_mentions",
            "stock_lifecycle_candidates",
            "stock_lifecycle_judgements",
            "stock_mention_status",
        } <= tables
        assert "strategy_snapshots" not in tables
        assert "strategy_snapshot_stocks" not in tables
        assert "strategy_snapshot_returns" not in tables
        assert "message_anchors" not in tables
        assert "message_anchor_status" not in tables
        assert "source_structures" not in tables
        assert "source_signal_snapshots" not in tables
        assert applied_migrations(conn) == {
            "001_init_messages",
            "002_init_runs",
            "003_message_fingerprint_index",
            "004_message_conversation_indexes",
            "005_message_source_time_index",
            "006_message_classifications",
            "007_message_anchors",
            "008_aggregate_refine_results",
            "009_recommendation_backtest",
            "010_recommendation_identity_sector",
            "012_view_cache",
            "013_source_radar",
            "014_anchor_status_trade_date_key",
            "015_drop_deprecated_source_radar",
            "016_stock_evidence_chain",
            "017_stock_mention_status",
            "018_stock_lifecycle_judgement_signature",
            "019_drop_deprecated_fermentation_strategy",
            "020_drop_message_anchor_tables",
        }
    finally:
        conn.close()


def test_market_db_migrations_are_independent(tmp_path):
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)

        tables = _tables(conn)
        assert {
            "schema_migrations",
            "tushare_cache",
            "tushare_history",
            "market_anchors",
            "market_anchor_members",
        } <= tables
        assert applied_migrations(conn) == {"001_init_market", "002_market_anchors"}
        assert "messages" not in tables
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "radar.sqlite3")
    try:
        migrate_message_db(conn)
        migrate_message_db(conn)

        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 19
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
    ).fetchall()
    return {row[0] for row in rows}
