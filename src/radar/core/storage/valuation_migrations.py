from __future__ import annotations

Migration = tuple[str, str]


VALUATION_MIGRATIONS: list[Migration] = [
    (
        "001_valuation_measurements",
        """
        CREATE TABLE IF NOT EXISTS valuation_measurements (
            measurement_id      TEXT PRIMARY KEY,
            report_id           TEXT NOT NULL,
            chat_run_id         TEXT NOT NULL UNIQUE,
            session_id          TEXT NOT NULL,
            source_generated_at TEXT,
            measured_at         TEXT NOT NULL,
            parse_status        TEXT NOT NULL,
            parse_error         TEXT,
            total_items         INTEGER NOT NULL DEFAULT 0,
            positive_count      INTEGER NOT NULL DEFAULT 0,
            notification_status TEXT,
            notified_at         TEXT,
            notification_error  TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_valuation_measurements_report
            ON valuation_measurements(report_id, measured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_valuation_measurements_positive
            ON valuation_measurements(positive_count, measured_at DESC);

        CREATE TABLE IF NOT EXISTS valuation_measurement_items (
            item_id          TEXT PRIMARY KEY,
            measurement_id   TEXT NOT NULL,
            row_order        INTEGER NOT NULL,
            rank             INTEGER,
            ts_code          TEXT,
            name             TEXT NOT NULL,
            current_mv_text  TEXT,
            target_mv_text   TEXT,
            upside_text      TEXT,
            valuation_status TEXT,
            confidence       TEXT,
            key_validation   TEXT,
            risk_flags       TEXT,
            data_gaps        TEXT,
            is_positive      INTEGER NOT NULL DEFAULT 0,
            raw_row_json     TEXT NOT NULL DEFAULT '{}',
            created_at       TEXT NOT NULL,
            FOREIGN KEY (measurement_id) REFERENCES valuation_measurements(measurement_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_valuation_items_measurement
            ON valuation_measurement_items(measurement_id, row_order);
        CREATE INDEX IF NOT EXISTS idx_valuation_items_ts_code
            ON valuation_measurement_items(ts_code);
        """,
    ),
    (
        "002_valuation_measurement_publication",
        """
        ALTER TABLE valuation_measurements
            ADD COLUMN published_url TEXT;
        ALTER TABLE valuation_measurements
            ADD COLUMN published_at TEXT;
        ALTER TABLE valuation_measurements
            ADD COLUMN publish_error TEXT;
        """,
    ),
]
