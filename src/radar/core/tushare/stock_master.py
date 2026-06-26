from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.storage import connect, migrate_market_db
from radar.core.tushare.client import call

STOCK_LIST_STATUSES = ("L", "D", "P")
STOCK_MASTER_FIELDS = "ts_code,symbol,name"


@dataclass(frozen=True)
class StockMasterRefreshResult:
    refreshed_at: datetime
    fetched_count: int
    stored_count: int
    listed_count: int
    delisted_count: int
    pending_count: int

    def metadata(self) -> dict[str, Any]:
        return {
            "refreshed_at": self.refreshed_at.isoformat(),
            "fetched_count": self.fetched_count,
            "stored_count": self.stored_count,
            "listed_count": self.listed_count,
            "delisted_count": self.delisted_count,
            "pending_count": self.pending_count,
        }


def refresh_stock_master(config: RadarConfig, *, force: bool = True) -> StockMasterRefreshResult:
    """全量刷新 A 股股票主数据；stocks 表是代码/名称映射的唯一业务表。"""

    refreshed_at = datetime.now()
    rows: list[dict[str, str]] = []
    for status in STOCK_LIST_STATUSES:
        rows.extend(_fetch_stock_basic(config, status, force=force))
    stored_rows = _dedupe_rows(rows)

    conn = connect(config.market_database_path)
    try:
        migrate_market_db(conn)
        replace_stock_master(conn, stored_rows, refreshed_at=refreshed_at)
    finally:
        conn.close()

    counts = _status_counts(stored_rows)
    return StockMasterRefreshResult(
        refreshed_at=refreshed_at,
        fetched_count=len(rows),
        stored_count=len(stored_rows),
        listed_count=counts.get("L", 0),
        delisted_count=counts.get("D", 0),
        pending_count=counts.get("P", 0),
    )


def replace_stock_master(
    conn: sqlite3.Connection,
    rows: list[dict[str, str]],
    *,
    refreshed_at: datetime,
) -> None:
    conn.execute("DELETE FROM stocks")
    conn.executemany(
        """
        INSERT INTO stocks (ts_code, symbol, name, list_status, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                row["ts_code"],
                row["symbol"],
                row["name"],
                row["list_status"],
                refreshed_at.isoformat(),
            )
            for row in rows
        ],
    )
    conn.commit()


def load_stock_master(conn: sqlite3.Connection, *, list_status: str | None = "L") -> list[dict[str, str]]:
    sql = "SELECT ts_code, symbol, name, list_status FROM stocks"
    params: tuple[str, ...] = ()
    if list_status is not None:
        sql += " WHERE list_status = ?"
        params = (list_status,)
    sql += " ORDER BY LENGTH(name) DESC, ts_code ASC"
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "ts_code": str(row["ts_code"]),
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "list_status": str(row["list_status"]),
        }
        for row in rows
    ]


def _fetch_stock_basic(config: RadarConfig, status: str, *, force: bool) -> list[dict[str, str]]:
    api_rows = call(
        config,
        "stock_basic",
        params={"list_status": status},
        fields=STOCK_MASTER_FIELDS,
        use_cache=not force,
    )
    rows: list[dict[str, str]] = []
    for item in api_rows:
        ts_code = str(item.get("ts_code") or "").strip().upper()
        symbol = str(item.get("symbol") or "").strip()
        name = str(item.get("name") or "").strip()
        if not ts_code or not symbol or not name:
            continue
        rows.append({"ts_code": ts_code, "symbol": symbol, "name": name, "list_status": status})
    return rows


def _dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_code: dict[str, dict[str, str]] = {}
    for row in rows:
        by_code[row["ts_code"]] = row
    return sorted(by_code.values(), key=lambda item: item["ts_code"])


def _status_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row["list_status"]
        counts[status] = counts.get(status, 0) + 1
    return counts
