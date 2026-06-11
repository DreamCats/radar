from __future__ import annotations

Migration = tuple[str, str]


EVIDENCE_CHAIN_MIGRATIONS: list[Migration] = [
    (
        "016_stock_evidence_chain",
        """
        CREATE TABLE IF NOT EXISTS stock_message_mentions (
            message_id             TEXT NOT NULL,
            ts_code                TEXT NOT NULL,
            stock_name             TEXT NOT NULL,
            symbol                 TEXT NOT NULL,
            message_time           TEXT NOT NULL,
            source                 TEXT NOT NULL,
            sender                 TEXT NOT NULL,
            group_name             TEXT,
            category               TEXT,
            fingerprint            TEXT NOT NULL,
            evidence_score         INTEGER NOT NULL DEFAULT 0,
            evidence_families_json TEXT NOT NULL DEFAULT '[]',
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL,
            PRIMARY KEY (message_id, ts_code),
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stock_mentions_code_time
            ON stock_message_mentions(ts_code, message_time);
        CREATE INDEX IF NOT EXISTS idx_stock_mentions_time
            ON stock_message_mentions(message_time);
        CREATE INDEX IF NOT EXISTS idx_stock_mentions_fingerprint
            ON stock_message_mentions(ts_code, fingerprint);

        CREATE TABLE IF NOT EXISTS stock_lifecycle_candidates (
            as_of_time          TEXT NOT NULL,
            window_start_time   TEXT NOT NULL,
            evidence_start_time TEXT NOT NULL,
            ts_code             TEXT NOT NULL,
            stock_name          TEXT NOT NULL,
            trigger_count       INTEGER NOT NULL,
            unique_trigger_count INTEGER NOT NULL,
            sender_count        INTEGER NOT NULL,
            conversation_count  INTEGER NOT NULL,
            evidence_score      INTEGER NOT NULL,
            channels_json       TEXT NOT NULL,
            family_counts_json  TEXT NOT NULL,
            rank                INTEGER NOT NULL,
            created_at          TEXT NOT NULL,
            PRIMARY KEY (as_of_time, ts_code)
        );

        CREATE INDEX IF NOT EXISTS idx_stock_lifecycle_candidates_rank
            ON stock_lifecycle_candidates(as_of_time, rank);

        CREATE TABLE IF NOT EXISTS stock_lifecycle_judgements (
            judgement_id        TEXT PRIMARY KEY,
            as_of_time          TEXT NOT NULL,
            window_start_time   TEXT NOT NULL,
            evidence_start_time TEXT NOT NULL,
            ts_code             TEXT NOT NULL,
            stock_name          TEXT NOT NULL,
            stage               TEXT NOT NULL,
            confidence          REAL,
            trigger_count       INTEGER NOT NULL,
            unique_trigger_count INTEGER NOT NULL,
            sender_count        INTEGER NOT NULL,
            conversation_count  INTEGER NOT NULL,
            evidence_count      INTEGER NOT NULL,
            channels_json       TEXT NOT NULL,
            evidence_refs_json  TEXT NOT NULL,
            llm_provider        TEXT,
            model               TEXT,
            prompt_version      TEXT NOT NULL,
            result_json         TEXT NOT NULL,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            UNIQUE (as_of_time, ts_code, prompt_version)
        );

        CREATE INDEX IF NOT EXISTS idx_stock_lifecycle_judgements_time
            ON stock_lifecycle_judgements(as_of_time, stage);
        CREATE INDEX IF NOT EXISTS idx_stock_lifecycle_judgements_code
            ON stock_lifecycle_judgements(ts_code, as_of_time);
        """,
    ),
    (
        "017_stock_mention_status",
        """
        CREATE TABLE IF NOT EXISTS stock_mention_status (
            message_id       TEXT PRIMARY KEY,
            matcher_version  TEXT NOT NULL,
            mention_count    INTEGER NOT NULL,
            indexed_at       TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stock_mention_status_version
            ON stock_mention_status(matcher_version, indexed_at);

        INSERT OR IGNORE INTO stock_mention_status (
            message_id, matcher_version, mention_count, indexed_at
        )
        SELECT
            message_id,
            'stock-evidence-v1',
            COUNT(*),
            datetime('now')
        FROM stock_message_mentions
        GROUP BY message_id;
        """,
    ),
    (
        "018_stock_lifecycle_judgement_signature",
        """
        ALTER TABLE stock_lifecycle_judgements
            ADD COLUMN evidence_signature TEXT;

        CREATE INDEX IF NOT EXISTS idx_stock_lifecycle_judgements_signature
            ON stock_lifecycle_judgements(ts_code, prompt_version, evidence_signature, updated_at);
        """,
    ),
]
