from __future__ import annotations

Migration = tuple[str, str]

REPORT_MIGRATIONS: list[Migration] = [
    (
        "001_catalyst_valuation_reports",
        """
        CREATE TABLE IF NOT EXISTS catalyst_valuation_reports (
            report_id TEXT PRIMARY KEY,
            run_id TEXT UNIQUE,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            granularity_minutes INTEGER,
            local_html_path TEXT NOT NULL,
            published_url TEXT,
            total_feed_items INTEGER NOT NULL,
            total_candidate_stocks INTEGER NOT NULL,
            total_stocks INTEGER NOT NULL,
            bark_sent_at TEXT,
            bark_error TEXT,
            request_json TEXT NOT NULL,
            report_json TEXT NOT NULL,
            rendered_html TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_catalyst_valuation_reports_generated_at
        ON catalyst_valuation_reports (generated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_catalyst_valuation_reports_window
        ON catalyst_valuation_reports (window_start, window_end);

        CREATE INDEX IF NOT EXISTS idx_catalyst_valuation_reports_granularity
        ON catalyst_valuation_reports (granularity_minutes);

        CREATE TABLE IF NOT EXISTS report_notifications (
            notification_id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (report_id) REFERENCES catalyst_valuation_reports(report_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_report_notifications_report_id
        ON report_notifications (report_id, sent_at DESC);
        """,
    ),
]
