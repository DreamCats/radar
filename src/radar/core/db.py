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
    (
        "007_message_anchors",
        """
        CREATE TABLE IF NOT EXISTS message_anchors (
            message_id        TEXT NOT NULL,
            anchor_id         TEXT NOT NULL,
            anchor_type       TEXT NOT NULL,
            name              TEXT NOT NULL,
            confidence        REAL NOT NULL,
            evidence_json     TEXT NOT NULL DEFAULT '[]',
            extractor_version TEXT NOT NULL,
            trade_date        TEXT NOT NULL,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            PRIMARY KEY (message_id, anchor_id, extractor_version),
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_message_anchors_anchor
            ON message_anchors(anchor_type, name, trade_date);
        CREATE INDEX IF NOT EXISTS idx_message_anchors_message
            ON message_anchors(message_id, extractor_version);

        CREATE TABLE IF NOT EXISTS message_anchor_status (
            message_id        TEXT NOT NULL,
            extractor_version TEXT NOT NULL,
            trade_date        TEXT NOT NULL,
            anchor_count      INTEGER NOT NULL,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            PRIMARY KEY (message_id, extractor_version),
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_message_anchor_status_version
            ON message_anchor_status(extractor_version, trade_date);
        """,
    ),
    (
        "008_aggregate_refine_results",
        """
        CREATE TABLE IF NOT EXISTS aggregate_refine_results (
            input_hash         TEXT PRIMARY KEY,
            run_id             TEXT NOT NULL,
            trade_date         TEXT NOT NULL,
            start_time         TEXT NOT NULL,
            end_time           TEXT NOT NULL,
            extractor_version  TEXT NOT NULL,
            prompt_version     TEXT NOT NULL,
            candidate_count    INTEGER NOT NULL,
            theme_count        INTEGER NOT NULL,
            result_json        TEXT NOT NULL,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_aggregate_refine_results_window
            ON aggregate_refine_results(trade_date, start_time, end_time, updated_at DESC);
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
        "011_strategy_snapshots",
        """
        CREATE TABLE IF NOT EXISTS strategy_snapshots (
            snapshot_id       TEXT PRIMARY KEY,
            strategy_type     TEXT NOT NULL,
            start_time        TEXT NOT NULL,
            end_time          TEXT NOT NULL,
            recent_start_time TEXT NOT NULL,
            generated_at      TEXT NOT NULL,
            created_at        TEXT NOT NULL,
            opportunity_count INTEGER NOT NULL,
            stock_count       INTEGER NOT NULL,
            payload_json      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_strategy_snapshots_generated
            ON strategy_snapshots(strategy_type, generated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_snapshots_window
            ON strategy_snapshots(strategy_type, end_time DESC);

        CREATE TABLE IF NOT EXISTS strategy_snapshot_stocks (
            snapshot_id                  TEXT NOT NULL,
            ts_code                      TEXT NOT NULL,
            stock_name                   TEXT NOT NULL,
            rank                         INTEGER NOT NULL,
            decision_bucket              TEXT NOT NULL,
            decision_reason              TEXT,
            realtime_score               REAL NOT NULL,
            credibility_level            TEXT,
            lifecycle_state              TEXT,
            price_position               TEXT,
            first_seen_time              TEXT,
            latest_message_time          TEXT,
            event_count                  INTEGER NOT NULL,
            source_count                 INTEGER NOT NULL,
            win_rate_t5                  REAL,
            average_excess_return_t5     REAL,
            first_source_name            TEXT,
            payload_json                 TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, ts_code),
            FOREIGN KEY (snapshot_id) REFERENCES strategy_snapshots(snapshot_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_strategy_snapshot_stocks_bucket
            ON strategy_snapshot_stocks(decision_bucket, realtime_score DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_snapshot_stocks_code
            ON strategy_snapshot_stocks(ts_code, snapshot_id);

        CREATE TABLE IF NOT EXISTS strategy_snapshot_returns (
            snapshot_id              TEXT NOT NULL,
            ts_code                  TEXT NOT NULL,
            window_days              INTEGER NOT NULL,
            benchmark_ts_code        TEXT NOT NULL,
            base_trade_date          TEXT,
            target_trade_date        TEXT,
            base_close               REAL,
            target_close             REAL,
            return_rate              REAL,
            benchmark_return_rate    REAL,
            excess_return_rate       REAL,
            max_drawdown_rate        REAL,
            status                   TEXT NOT NULL,
            error_message            TEXT,
            updated_at               TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, ts_code, window_days, benchmark_ts_code),
            FOREIGN KEY (snapshot_id, ts_code)
                REFERENCES strategy_snapshot_stocks(snapshot_id, ts_code) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_strategy_snapshot_returns_status
            ON strategy_snapshot_returns(status, updated_at DESC);
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
