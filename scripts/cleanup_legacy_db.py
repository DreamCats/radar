#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from radar.core.config import load_config
from radar.core.scheduler.defaults import RETIRED_SCHEDULE_IDS, RETIRED_SCHEDULE_JOB_KEYS
from radar.core.storage.db import migrate_market_db, migrate_message_db


LEGACY_MESSAGE_TABLES = (
    "message_classifications",
    "message_anchor_status",
    "message_anchors",
    "aggregate_refine_results",
    "recommendation_backtest_windows",
    "recommendation_events",
    "source_signal_snapshots",
    "source_structures",
    "strategy_snapshot_returns",
    "strategy_snapshot_stocks",
    "strategy_snapshots",
    "opportunity_lifecycle_digests",
    "stock_lifecycle_judgements",
    "stock_lifecycle_candidates",
    "stock_mention_status",
    "stock_message_mentions",
    "view_cache",
)

LEGACY_MARKET_TABLES = (
    "stock_theme_memberships",
    "theme_source_links",
    "theme_nodes",
    "market_anchor_member_spans",
    "market_anchor_current_members",
    "market_anchor_members",
    "market_anchors",
)

CURRENT_ANALYST_MENTION_COLUMNS = (
    "mention_id",
    "message_id",
    "source",
    "sender",
    "analyst_id",
    "analyst_display_name",
    "analyst_alias_key",
    "group_name",
    "ts_code",
    "stock_name",
    "symbol",
    "message_time",
    "event_date",
    "evidence_snippet",
    "content_fingerprint",
    "extractor_version",
    "stock_count_in_message",
    "quality_flags",
    "is_effective",
    "dedupe_key",
    "dedupe_reason",
    "created_at",
    "updated_at",
)

DEFAULT_VALUES = {
    "group_name": "NULL",
    "stock_count_in_message": "1",
    "quality_flags": "'[]'",
    "is_effective": "1",
    "dedupe_reason": "NULL",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 radar 旧功能遗留 DB 表，并重置 migration 账本。")
    parser.add_argument("--config-dir", type=Path, default=None, help="radar 配置目录，默认读取 RADAR_CONFIG_DIR 或 ~/.config/radar")
    parser.add_argument("--no-vacuum", action="store_true", help="只清理表结构，不回收 SQLite 空闲页")
    args = parser.parse_args()

    config = load_config(args.config_dir)
    message_summary = cleanup_message_db(config.database_path, vacuum=not args.no_vacuum)
    market_summary = cleanup_market_db(config.market_database_path, vacuum=not args.no_vacuum)

    print(f"message_db={config.database_path}")
    print(f"message_dropped={','.join(message_summary.dropped_tables) or '(none)'}")
    print(f"message_rebuilt_analyst_mentions={message_summary.rebuilt_analyst_mentions}")
    print(f"market_db={config.market_database_path}")
    print(f"market_dropped={','.join(market_summary.dropped_tables) or '(none)'}")
    return 0


class CleanupSummary:
    def __init__(self, dropped_tables: list[str], *, rebuilt_analyst_mentions: bool = False) -> None:
        self.dropped_tables = dropped_tables
        self.rebuilt_analyst_mentions = rebuilt_analyst_mentions


def cleanup_message_db(path: Path, *, vacuum: bool) -> CleanupSummary:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = OFF")
        rebuilt = rebuild_analyst_mentions(conn)
        dropped = drop_existing_tables(conn, LEGACY_MESSAGE_TABLES)
        delete_retired_schedules(conn)
        delete_if_table_exists(
            conn,
            "runs",
            """
            kind IN (
                'aggregate_refine',
                'aggregate_topics',
                'message_anchor_range',
                'recommendation_backtest_refresh',
                'source_extract',
                'source_radar_snapshot',
                'stock_evidence_chain',
                'opportunity_lifecycle_digest',
                'strategy_snapshot_backfill'
            )
            OR target LIKE 'opportunity_signal:%'
            """,
        )
        reset_migration_ledger(conn)
        migrate_message_db(conn)
        check_integrity(conn, path)
        if vacuum:
            conn.execute("VACUUM")
        return CleanupSummary(dropped, rebuilt_analyst_mentions=rebuilt)
    finally:
        conn.close()


def cleanup_market_db(path: Path, *, vacuum: bool) -> CleanupSummary:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        dropped = drop_existing_tables(conn, LEGACY_MARKET_TABLES)
        reset_migration_ledger(conn)
        migrate_market_db(conn)
        check_integrity(conn, path)
        if vacuum:
            conn.execute("VACUUM")
        return CleanupSummary(dropped)
    finally:
        conn.close()


def rebuild_analyst_mentions(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "analyst_stock_mentions"):
        return False

    old_columns = table_columns(conn, "analyst_stock_mentions")
    if "mention_id" not in old_columns:
        return False

    conn.executescript(
        """
        DROP TABLE IF EXISTS analyst_stock_mentions_rebuild;

        CREATE TABLE analyst_stock_mentions_rebuild (
            mention_id                TEXT PRIMARY KEY,
            message_id                TEXT NOT NULL,
            source                    TEXT NOT NULL,
            sender                    TEXT NOT NULL,
            analyst_id                TEXT NOT NULL,
            analyst_display_name      TEXT NOT NULL,
            analyst_alias_key         TEXT NOT NULL,
            group_name                TEXT,
            ts_code                   TEXT NOT NULL,
            stock_name                TEXT NOT NULL,
            symbol                    TEXT NOT NULL,
            message_time              TEXT NOT NULL,
            event_date                TEXT NOT NULL,
            evidence_snippet          TEXT NOT NULL,
            content_fingerprint       TEXT NOT NULL,
            extractor_version         TEXT NOT NULL,
            stock_count_in_message    INTEGER NOT NULL DEFAULT 1,
            quality_flags             TEXT NOT NULL DEFAULT '[]',
            is_effective              INTEGER NOT NULL DEFAULT 1,
            dedupe_key                TEXT NOT NULL,
            dedupe_reason             TEXT,
            created_at                TEXT NOT NULL,
            updated_at                TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );
        """
    )

    columns = ", ".join(CURRENT_ANALYST_MENTION_COLUMNS)
    select_exprs = ", ".join(select_expr(column, old_columns) for column in CURRENT_ANALYST_MENTION_COLUMNS)
    conn.execute(
        f"""
        INSERT OR IGNORE INTO analyst_stock_mentions_rebuild ({columns})
        SELECT {select_exprs}
        FROM analyst_stock_mentions
        """
    )
    conn.execute("DROP TABLE analyst_stock_mentions")
    conn.execute("ALTER TABLE analyst_stock_mentions_rebuild RENAME TO analyst_stock_mentions")
    return True


def select_expr(column: str, old_columns: set[str]) -> str:
    if column in old_columns:
        return f'"{column}"'
    return DEFAULT_VALUES.get(column, "''")


def drop_existing_tables(conn: sqlite3.Connection, names: Iterable[str]) -> list[str]:
    dropped: list[str] = []
    for name in names:
        if table_exists(conn, name):
            dropped.append(name)
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    conn.commit()
    return dropped


def delete_retired_schedules(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "job_schedules"):
        return
    has_tick_table = table_exists(conn, "job_schedule_ticks")
    delete_schedule_rows_by_ids(conn, RETIRED_SCHEDULE_IDS, has_tick_table=has_tick_table)
    delete_schedule_rows_by_job_keys(conn, RETIRED_SCHEDULE_JOB_KEYS, has_tick_table=has_tick_table)
    conn.commit()


def delete_schedule_rows_by_ids(
    conn: sqlite3.Connection,
    schedule_ids: Iterable[str],
    *,
    has_tick_table: bool,
) -> None:
    ids = tuple(schedule_ids)
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    if has_tick_table:
        conn.execute(f"DELETE FROM job_schedule_ticks WHERE schedule_id IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM job_schedules WHERE schedule_id IN ({placeholders})", ids)


def delete_schedule_rows_by_job_keys(
    conn: sqlite3.Connection,
    job_keys: Iterable[str],
    *,
    has_tick_table: bool,
) -> None:
    keys = tuple(job_keys)
    if not keys:
        return
    placeholders = ", ".join("?" for _ in keys)
    if has_tick_table:
        conn.execute(
            f"""
            DELETE FROM job_schedule_ticks
            WHERE schedule_id IN (
                SELECT schedule_id FROM job_schedules WHERE job_key IN ({placeholders})
            )
            """,
            keys,
        )
    conn.execute(f"DELETE FROM job_schedules WHERE job_key IN ({placeholders})", keys)


def delete_if_table_exists(conn: sqlite3.Connection, table: str, where_sql: str) -> None:
    if table_exists(conn, table):
        conn.execute(f'DELETE FROM "{table}" WHERE {where_sql}')
        conn.commit()


def reset_migration_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.execute("DELETE FROM schema_migrations")
    conn.commit()


def check_integrity(conn: sqlite3.Connection, path: Path) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"{path} integrity_check failed: {result}")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


if __name__ == "__main__":
    raise SystemExit(main())
