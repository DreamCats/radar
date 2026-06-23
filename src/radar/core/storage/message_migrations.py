from __future__ import annotations

from radar.core.storage.evidence_migrations import (
    EVIDENCE_CHAIN_MIGRATIONS,
    LIFECYCLE_DIGEST_MIGRATIONS,
)

Migration = tuple[str, str]


BASE_MESSAGE_MIGRATIONS: list[Migration] = [
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
]


MESSAGE_CLEANUP_MIGRATIONS: list[Migration] = [

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

ANALYST_MENTION_MIGRATIONS: list[Migration] = [
    (
        "024_analyst_stock_mentions",
        """
        CREATE TABLE IF NOT EXISTS analyst_stock_mentions (
            mention_id                TEXT PRIMARY KEY,
            message_id                TEXT NOT NULL,
            source                    TEXT NOT NULL,
            sender                    TEXT NOT NULL,
            analyst_id                TEXT NOT NULL,
            analyst_display_name      TEXT NOT NULL,
            analyst_alias_key         TEXT NOT NULL,
            group_name                TEXT,
            category                  TEXT NOT NULL,
            classification_confidence REAL NOT NULL,
            ts_code                   TEXT NOT NULL,
            stock_name                TEXT NOT NULL,
            symbol                    TEXT NOT NULL,
            message_time              TEXT NOT NULL,
            event_date                TEXT NOT NULL,
            evidence_snippet          TEXT NOT NULL,
            content_fingerprint       TEXT NOT NULL,
            extractor_version         TEXT NOT NULL,
            is_effective              INTEGER NOT NULL DEFAULT 1,
            dedupe_key                TEXT NOT NULL,
            dedupe_reason             TEXT,
            created_at                TEXT NOT NULL,
            updated_at                TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_analyst_stock_mentions_unique
            ON analyst_stock_mentions(message_id, ts_code, extractor_version);
        CREATE INDEX IF NOT EXISTS idx_analyst_stock_mentions_time
            ON analyst_stock_mentions(message_time DESC, mention_id);
        CREATE INDEX IF NOT EXISTS idx_analyst_stock_mentions_analyst
            ON analyst_stock_mentions(analyst_id, is_effective, message_time DESC);
        CREATE INDEX IF NOT EXISTS idx_analyst_stock_mentions_stock
            ON analyst_stock_mentions(ts_code, message_time DESC);

        CREATE TABLE IF NOT EXISTS analyst_stock_mention_windows (
            mention_id                  TEXT NOT NULL,
            window_days                 INTEGER NOT NULL,
            benchmark_ts_code           TEXT NOT NULL,
            base_trade_date             TEXT,
            target_trade_date           TEXT,
            base_close                  REAL,
            target_close                REAL,
            return_rate                 REAL,
            positive                    INTEGER,
            benchmark_base_close        REAL,
            benchmark_target_close      REAL,
            benchmark_return_rate       REAL,
            excess_return_rate          REAL,
            status                      TEXT NOT NULL,
            error_message               TEXT,
            updated_at                  TEXT NOT NULL,
            PRIMARY KEY (mention_id, window_days, benchmark_ts_code),
            FOREIGN KEY (mention_id) REFERENCES analyst_stock_mentions(mention_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_analyst_stock_mention_windows_status
            ON analyst_stock_mention_windows(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_analyst_stock_mention_windows_window
            ON analyst_stock_mention_windows(window_days, benchmark_ts_code, status);
        """,
    ),
    (
        "025_analyst_stock_mention_quality_flags",
        """
        ALTER TABLE analyst_stock_mentions
            ADD COLUMN stock_count_in_message INTEGER NOT NULL DEFAULT 1;

        ALTER TABLE analyst_stock_mentions
            ADD COLUMN quality_flags TEXT NOT NULL DEFAULT '[]';
        """,
    ),
    (
        "026_drop_recommendation_backtest",
        """
        DROP TABLE IF EXISTS recommendation_backtest_windows;
        DROP TABLE IF EXISTS recommendation_events;

        DELETE FROM view_cache
        WHERE dependency_key LIKE '%recommendation_events%'
           OR dependency_key LIKE '%recommendation_backtest_windows%';

        DELETE FROM runs
        WHERE kind = 'recommendation_backtest_refresh';
        """,
    ),
]


MESSAGE_MIGRATIONS = (
    BASE_MESSAGE_MIGRATIONS
    + EVIDENCE_CHAIN_MIGRATIONS
    + MESSAGE_CLEANUP_MIGRATIONS
    + LIFECYCLE_DIGEST_MIGRATIONS
    + ANALYST_MENTION_MIGRATIONS
)
