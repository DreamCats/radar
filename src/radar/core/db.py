from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence

from radar.core.db_evidence_chain import EVIDENCE_CHAIN_MIGRATIONS

Migration = tuple[str, str]
_MIGRATION_LOCK = threading.Lock()


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
    (
        "007_message_anchors",
        """
        -- Deprecated: message-level anchor extraction has been removed.
        """,
    ),
    (
        "008_aggregate_refine_results",
        """
        -- Deprecated: aggregate refine has been removed.
        """,
    ),
    (
        "009_recommendation_backtest",
        """
        CREATE TABLE IF NOT EXISTS recommendation_events (
            event_id                  TEXT PRIMARY KEY,
            message_id                TEXT NOT NULL,
            source                    TEXT NOT NULL,
            source_candidate          TEXT NOT NULL,
            group_name                TEXT,
            category                  TEXT NOT NULL,
            classification_confidence REAL NOT NULL,
            ts_code                   TEXT NOT NULL,
            stock_name                TEXT NOT NULL,
            action                    TEXT NOT NULL,
            message_time              TEXT NOT NULL,
            event_date                TEXT NOT NULL,
            extractor_version         TEXT NOT NULL,
            anchor_confidence         REAL NOT NULL,
            created_at                TEXT NOT NULL,
            updated_at                TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendation_events_unique
            ON recommendation_events(message_id, ts_code, action, extractor_version);
        CREATE INDEX IF NOT EXISTS idx_recommendation_events_time
            ON recommendation_events(message_time DESC, event_id);
        CREATE INDEX IF NOT EXISTS idx_recommendation_events_source_stock
            ON recommendation_events(source_candidate, ts_code, event_date);

        CREATE TABLE IF NOT EXISTS recommendation_backtest_windows (
            event_id                    TEXT NOT NULL,
            window_days                 INTEGER NOT NULL,
            benchmark_ts_code           TEXT NOT NULL,
            base_trade_date             TEXT,
            target_trade_date           TEXT,
            base_close                  REAL,
            target_close                REAL,
            return_rate                 REAL,
            win                         INTEGER,
            benchmark_base_close        REAL,
            benchmark_target_close      REAL,
            benchmark_return_rate       REAL,
            excess_return_rate          REAL,
            status                      TEXT NOT NULL,
            error_message               TEXT,
            updated_at                  TEXT NOT NULL,
            PRIMARY KEY (event_id, window_days, benchmark_ts_code),
            FOREIGN KEY (event_id) REFERENCES recommendation_events(event_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_recommendation_backtest_status
            ON recommendation_backtest_windows(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_recommendation_backtest_window
            ON recommendation_backtest_windows(window_days, benchmark_ts_code, status);
        """,
    ),
    (
        "010_recommendation_identity_sector",
        """
        CREATE TABLE IF NOT EXISTS analysts (
            analyst_id     TEXT PRIMARY KEY,
            display_name   TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analyst_aliases (
            alias_text     TEXT PRIMARY KEY,
            alias_key      TEXT NOT NULL,
            analyst_id     TEXT NOT NULL,
            confidence     REAL NOT NULL,
            method         TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            FOREIGN KEY (analyst_id) REFERENCES analysts(analyst_id) ON DELETE CASCADE
        );

        ALTER TABLE recommendation_events ADD COLUMN analyst_id TEXT;
        ALTER TABLE recommendation_events ADD COLUMN analyst_display_name TEXT;
        ALTER TABLE recommendation_events ADD COLUMN analyst_alias_key TEXT;
        ALTER TABLE recommendation_events ADD COLUMN sector_anchor_id TEXT;
        ALTER TABLE recommendation_events ADD COLUMN sector_anchor_type TEXT;
        ALTER TABLE recommendation_events ADD COLUMN sector_name TEXT;
        ALTER TABLE recommendation_events ADD COLUMN sector_confidence REAL;

        CREATE INDEX IF NOT EXISTS idx_analyst_aliases_key
            ON analyst_aliases(alias_key, analyst_id);
        CREATE INDEX IF NOT EXISTS idx_recommendation_events_analyst_stock
            ON recommendation_events(analyst_id, ts_code, event_date);
        CREATE INDEX IF NOT EXISTS idx_recommendation_events_sector
            ON recommendation_events(sector_anchor_type, sector_name, event_date);
        """,
    ),
    (
        "012_view_cache",
        """
        CREATE TABLE IF NOT EXISTS view_cache (
            cache_key      TEXT PRIMARY KEY,
            dependency_key TEXT NOT NULL,
            payload_json   TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            expires_at     TEXT,
            compute_ms     INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_view_cache_created
            ON view_cache(created_at DESC);
        """,
    ),
    (
        "013_source_radar",
        """
        CREATE TABLE IF NOT EXISTS source_structures (
            structure_id       TEXT PRIMARY KEY,
            message_id         TEXT NOT NULL,
            source             TEXT NOT NULL,
            sender             TEXT NOT NULL,
            group_name         TEXT,
            message_time       TEXT NOT NULL,
            is_candidate       INTEGER NOT NULL,
            anchor_span        TEXT NOT NULL DEFAULT '',
            modifier_span      TEXT NOT NULL DEFAULT '',
            novel_span         TEXT NOT NULL DEFAULT '',
            relation_type      TEXT NOT NULL DEFAULT 'other',
            relation_evidence  TEXT NOT NULL DEFAULT '',
            ask_question       TEXT NOT NULL DEFAULT '',
            confidence         REAL NOT NULL DEFAULT 0,
            reject_reason      TEXT,
            llm_provider       TEXT,
            prompt_version     TEXT NOT NULL,
            extractor_version  TEXT NOT NULL,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_structures_unique
            ON source_structures(message_id, anchor_span, modifier_span, novel_span, relation_type, extractor_version);
        CREATE INDEX IF NOT EXISTS idx_source_structures_time
            ON source_structures(message_time DESC, structure_id);
        CREATE INDEX IF NOT EXISTS idx_source_structures_candidate
            ON source_structures(is_candidate, confidence DESC);

        CREATE TABLE IF NOT EXISTS source_signal_snapshots (
            snapshot_id       TEXT PRIMARY KEY,
            signal_id         TEXT NOT NULL,
            status            TEXT NOT NULL,
            anchor_span       TEXT NOT NULL,
            modifier_span     TEXT NOT NULL,
            novel_span        TEXT NOT NULL,
            relation_type     TEXT NOT NULL,
            score             REAL NOT NULL,
            novelty_strength  REAL NOT NULL,
            earliness_score   REAL NOT NULL,
            askability_score  REAL NOT NULL,
            trade_score       REAL NOT NULL,
            first_message_id  TEXT NOT NULL,
            first_seen_time   TEXT NOT NULL,
            as_of_time        TEXT NOT NULL,
            payload_json      TEXT NOT NULL,
            created_at        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_source_signal_snapshots_asof
            ON source_signal_snapshots(as_of_time DESC, status, score DESC);
        CREATE INDEX IF NOT EXISTS idx_source_signal_snapshots_signal
            ON source_signal_snapshots(signal_id, as_of_time DESC);
        """,
    ),
    (
        "014_anchor_status_trade_date_key",
        """
        -- Deprecated: message-level anchor extraction has been removed.
        """,
    ),
    (
        "015_drop_deprecated_source_radar",
        """
        DROP TABLE IF EXISTS source_signal_snapshots;
        DROP TABLE IF EXISTS source_structures;

        DELETE FROM view_cache
        WHERE cache_key LIKE 'strategy.source_radar%';

        DELETE FROM runs
        WHERE kind IN ('source_extract', 'source_radar_snapshot');
        """,
    ),
] + EVIDENCE_CHAIN_MIGRATIONS + [
    (
        "019_drop_deprecated_fermentation_strategy",
        """
        DROP TABLE IF EXISTS strategy_snapshot_returns;
        DROP TABLE IF EXISTS strategy_snapshot_stocks;
        DROP TABLE IF EXISTS strategy_snapshots;

        DELETE FROM view_cache
        WHERE cache_key LIKE 'strategy.opportunities%'
           OR cache_key LIKE 'strategy.validation%';

        DELETE FROM runs
        WHERE kind = 'strategy_snapshot_backfill'
           OR target LIKE 'opportunity_signal:%';
        """,
    ),
    (
        "020_drop_message_anchor_tables",
        """
        DROP TABLE IF EXISTS message_anchor_status;
        DROP TABLE IF EXISTS message_anchors;

        DELETE FROM view_cache
        WHERE dependency_key LIKE '%message_anchors%';

        DELETE FROM runs
        WHERE kind = 'message_anchor_range';
        """,
    ),
    (
        "021_drop_deprecated_aggregate_and_anchor_backtests",
        """
        DELETE FROM recommendation_backtest_windows
        WHERE event_id IN (
            SELECT event_id
            FROM recommendation_events
            WHERE extractor_version <> 'lifecycle-evidence-v1'
        );

        DELETE FROM recommendation_events
        WHERE extractor_version <> 'lifecycle-evidence-v1';

        DROP TABLE IF EXISTS aggregate_refine_results;

        DELETE FROM view_cache
        WHERE cache_key LIKE 'organize.aggregate%'
           OR dependency_key LIKE '%aggregate_refine_results%';

        DELETE FROM runs
        WHERE kind IN ('aggregate_refine', 'aggregate_topics');
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
    (
        "002_market_anchors",
        """
        CREATE TABLE IF NOT EXISTS market_anchors (
            anchor_id     TEXT PRIMARY KEY,
            anchor_type   TEXT NOT NULL,
            name          TEXT NOT NULL,
            aliases_json  TEXT NOT NULL DEFAULT '[]',
            source        TEXT NOT NULL,
            source_code   TEXT NOT NULL DEFAULT '',
            trade_date    TEXT NOT NULL,
            hot_score     REAL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_market_anchors_type_name
            ON market_anchors(anchor_type, name);
        CREATE INDEX IF NOT EXISTS idx_market_anchors_source_date
            ON market_anchors(source, trade_date);

        CREATE TABLE IF NOT EXISTS market_anchor_members (
            anchor_id     TEXT NOT NULL,
            ts_code       TEXT NOT NULL,
            stock_name    TEXT NOT NULL,
            reason        TEXT,
            source        TEXT NOT NULL,
            trade_date    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (anchor_id, ts_code, source, trade_date),
            FOREIGN KEY (anchor_id) REFERENCES market_anchors(anchor_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_market_anchor_members_stock
            ON market_anchor_members(ts_code, trade_date);
        """,
    ),
    (
        "003_market_anchor_derivatives",
        """
        CREATE TABLE IF NOT EXISTS market_anchor_current_members (
            anchor_key           TEXT NOT NULL,
            anchor_type          TEXT NOT NULL,
            anchor_name          TEXT NOT NULL,
            anchor_source        TEXT NOT NULL,
            source_code          TEXT NOT NULL DEFAULT '',
            member_source        TEXT NOT NULL,
            ts_code              TEXT NOT NULL,
            stock_name           TEXT NOT NULL,
            reason               TEXT,
            latest_trade_date    TEXT NOT NULL,
            hot_score            REAL,
            anchor_metadata_json TEXT NOT NULL DEFAULT '{}',
            member_metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at           TEXT NOT NULL,
            PRIMARY KEY (anchor_key, member_source, ts_code)
        );

        CREATE INDEX IF NOT EXISTS idx_market_anchor_current_members_stock
            ON market_anchor_current_members(ts_code, latest_trade_date);
        CREATE INDEX IF NOT EXISTS idx_market_anchor_current_members_anchor
            ON market_anchor_current_members(anchor_key, latest_trade_date);

        CREATE TABLE IF NOT EXISTS market_anchor_member_spans (
            anchor_key           TEXT NOT NULL,
            anchor_type          TEXT NOT NULL,
            anchor_name          TEXT NOT NULL,
            anchor_source        TEXT NOT NULL,
            source_code          TEXT NOT NULL DEFAULT '',
            member_source        TEXT NOT NULL,
            ts_code              TEXT NOT NULL,
            stock_name           TEXT NOT NULL,
            first_seen_date      TEXT NOT NULL,
            last_seen_date       TEXT NOT NULL,
            seen_days            INTEGER NOT NULL,
            latest_reason        TEXT,
            latest_hot_score     REAL,
            anchor_metadata_json TEXT NOT NULL DEFAULT '{}',
            member_metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at           TEXT NOT NULL,
            PRIMARY KEY (anchor_key, member_source, ts_code)
        );

        CREATE INDEX IF NOT EXISTS idx_market_anchor_member_spans_stock
            ON market_anchor_member_spans(ts_code, last_seen_date);
        CREATE INDEX IF NOT EXISTS idx_market_anchor_member_spans_anchor
            ON market_anchor_member_spans(anchor_key, last_seen_date);
        """,
    ),
    (
        "004_market_theme_normalization",
        """
        CREATE TABLE IF NOT EXISTS theme_nodes (
            theme_id            TEXT PRIMARY KEY,
            theme_name          TEXT NOT NULL,
            theme_type          TEXT NOT NULL,
            parent_theme_id     TEXT,
            aliases_json        TEXT NOT NULL DEFAULT '[]',
            policy_tags_json    TEXT NOT NULL DEFAULT '[]',
            status              TEXT NOT NULL DEFAULT 'active',
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_theme_nodes_type
            ON theme_nodes(theme_type, status);

        CREATE TABLE IF NOT EXISTS theme_source_links (
            theme_id            TEXT NOT NULL,
            source              TEXT NOT NULL,
            source_code         TEXT NOT NULL,
            source_name         TEXT NOT NULL,
            source_anchor_type  TEXT NOT NULL,
            confidence          REAL NOT NULL DEFAULT 1.0,
            first_seen_date     TEXT NOT NULL,
            last_seen_date      TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            PRIMARY KEY (source, source_code, source_anchor_type, theme_id)
        );

        CREATE INDEX IF NOT EXISTS idx_theme_source_links_theme
            ON theme_source_links(theme_id, last_seen_date);

        CREATE TABLE IF NOT EXISTS stock_theme_memberships (
            theme_id            TEXT NOT NULL,
            ts_code             TEXT NOT NULL,
            stock_name          TEXT NOT NULL,
            role                TEXT NOT NULL DEFAULT 'unknown',
            confidence          REAL NOT NULL DEFAULT 0.5,
            source_count        INTEGER NOT NULL DEFAULT 0,
            sources_json        TEXT NOT NULL DEFAULT '[]',
            reasons_json        TEXT NOT NULL DEFAULT '[]',
            first_seen_date     TEXT NOT NULL,
            last_seen_date      TEXT NOT NULL,
            latest_trade_date   TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            PRIMARY KEY (theme_id, ts_code)
        );

        CREATE INDEX IF NOT EXISTS idx_stock_theme_memberships_stock
            ON stock_theme_memberships(ts_code, latest_trade_date);
        CREATE INDEX IF NOT EXISTS idx_stock_theme_memberships_theme
            ON stock_theme_memberships(theme_id, latest_trade_date, confidence);
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
