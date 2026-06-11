from __future__ import annotations

Migration = tuple[str, str]


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
