from __future__ import annotations

Migration = tuple[str, str]


MESSAGE_MIGRATIONS: list[Migration] = [
    (
        "001_message_schema",
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
        CREATE INDEX IF NOT EXISTS idx_messages_fingerprint_lookup
            ON messages(source, sender, message_time, group_name);
        CREATE INDEX IF NOT EXISTS idx_messages_group_conversation
            ON messages(source, group_name, message_time DESC, message_id DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_sender_conversation
            ON messages(source, sender, message_time DESC, message_id DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_source_time
            ON messages(source, message_time DESC, message_id DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            message_id UNINDEXED,
            raw_content,
            sender,
            group_name,
            tokenize = 'trigram'
        );

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

        CREATE INDEX IF NOT EXISTS idx_analyst_aliases_key
            ON analyst_aliases(alias_key, analyst_id);

        CREATE TABLE IF NOT EXISTS analyst_stock_mentions (
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

        CREATE TABLE IF NOT EXISTS job_schedules (
            schedule_id TEXT PRIMARY KEY,
            job_key TEXT NOT NULL,
            title TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            cadence_kind TEXT NOT NULL,
            cadence_json TEXT NOT NULL DEFAULT '{}',
            window_preset TEXT,
            request_json TEXT NOT NULL DEFAULT '{}',
            catch_up_policy TEXT NOT NULL DEFAULT 'latest_only',
            max_lag_minutes INTEGER NOT NULL DEFAULT 60,
            last_tick_at TEXT,
            next_tick_at TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_job_schedules_enabled_next
            ON job_schedules(enabled, next_tick_at);

        CREATE TABLE IF NOT EXISTS job_schedule_ticks (
            tick_id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            planned_at TEXT NOT NULL,
            fired_at TEXT,
            status TEXT NOT NULL,
            run_ids_json TEXT NOT NULL DEFAULT '[]',
            request_json TEXT NOT NULL DEFAULT '{}',
            skipped_reason TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (schedule_id) REFERENCES job_schedules(schedule_id)
        );

        CREATE INDEX IF NOT EXISTS idx_job_schedule_ticks_schedule_created
            ON job_schedule_ticks(schedule_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_job_schedule_ticks_status_created
            ON job_schedule_ticks(status, created_at DESC);
        """,
    ),
]
