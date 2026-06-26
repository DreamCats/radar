from __future__ import annotations

Migration = tuple[str, str]


MARKET_MIGRATIONS: list[Migration] = [
    (
        "001_market_schema",
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
        "002_stock_master",
        """
        CREATE TABLE IF NOT EXISTS stocks (
            ts_code     TEXT PRIMARY KEY,
            symbol      TEXT NOT NULL,
            name        TEXT NOT NULL,
            list_status TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stocks_symbol
            ON stocks(symbol);
        CREATE INDEX IF NOT EXISTS idx_stocks_name
            ON stocks(name);
        CREATE INDEX IF NOT EXISTS idx_stocks_status
            ON stocks(list_status, ts_code);
        """,
    ),
]
