from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


DEFAULT_TTL = 86_400

# 准静态接口给长 TTL，当日盘中接口给短 TTL；历史接口另走 history.py。
TTL_BY_API: dict[str, int] = {
    "stock_basic": 7 * 86_400,
    "stock_company": 7 * 86_400,
    "fut_basic": 7 * 86_400,
    "cb_basic": 7 * 86_400,
    "fund_basic": 7 * 86_400,
    "index_basic": 7 * 86_400,
    "fund_manager": 7 * 86_400,
    "trade_cal": 30 * 86_400,
    "dc_index": 7 * 86_400,
    "ths_index": 7 * 86_400,
    "dc_member": 86_400,
    "ths_member": 86_400,
    "top_list": 3_600,
    "top_inst": 3_600,
    "limit_list_d": 3_600,
    "limit_step": 3_600,
    "limit_strongest": 3_600,
    "ths_hot": 1_800,
    "dc_hot": 1_800,
}


def ttl_for(api_name: str) -> int:
    return TTL_BY_API.get(api_name, DEFAULT_TTL)


def get(
    database: Path,
    api_name: str,
    params: dict[str, Any],
    *,
    fields: str | list[str] | None = None,
    ttl: int = DEFAULT_TTL,
) -> list[dict[str, Any]] | None:
    """命中返回 rows，未命中或过期返回 None。"""

    if ttl <= 0:
        return None
    with _connect(database) as conn:
        row = conn.execute(
            "SELECT fetched_at, data FROM tushare_cache WHERE key=?",
            (_key(api_name, params, fields),),
        ).fetchone()
    if row is None:
        return None
    fetched_at, data = row
    if time.time() - fetched_at > ttl:
        return None
    return json.loads(data)


def put(
    database: Path,
    api_name: str,
    params: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    fields: str | list[str] | None = None,
) -> None:
    payload = json.dumps(rows, ensure_ascii=False, default=str)
    with _connect(database) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tushare_cache (key, api_name, fetched_at, data)"
            " VALUES (?, ?, ?, ?)",
            (_key(api_name, params, fields), api_name, int(time.time()), payload),
        )


def clear(database: Path, api_name: str | None = None) -> int:
    with _connect(database) as conn:
        if api_name:
            cur = conn.execute("DELETE FROM tushare_cache WHERE api_name=?", (api_name,))
        else:
            cur = conn.execute("DELETE FROM tushare_cache")
        return cur.rowcount


def _key(api_name: str, params: dict[str, Any], fields: str | list[str] | None) -> str:
    field_key = ",".join(fields) if isinstance(fields, list) else fields
    raw = json.dumps(
        {"api": api_name, "fields": field_key, "params": params},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tushare_cache (
            key        TEXT PRIMARY KEY,
            api_name   TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            data       TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tushare_cache_api ON tushare_cache(api_name)")
    return conn
