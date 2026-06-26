from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from radar.core.storage.db import SQLITE_TIMEOUT_SECONDS, configure_sqlite_connection, migrate_market_db
from radar.core.tushare.models import HistorySpec


POST_CLOSE_CACHE_TIME = dt.time(15, 30)

SPECS: dict[str, HistorySpec] = {
    # 第一版只纳入低风险的一维时间序列；多维接口先走 KV，避免行缓存主键覆盖。
    "daily": HistorySpec("daily", "trade_date", "day"),
    "weekly": HistorySpec("weekly", "trade_date", "day"),
    "monthly": HistorySpec("monthly", "trade_date", "day"),
    "daily_basic": HistorySpec("daily_basic", "trade_date", "day"),
    "adj_factor": HistorySpec("adj_factor", "trade_date", "day"),
    "moneyflow": HistorySpec("moneyflow", "trade_date", "day"),
    "moneyflow_dc": HistorySpec("moneyflow_dc", "trade_date", "day"),
    "moneyflow_ths": HistorySpec("moneyflow_ths", "trade_date", "day"),
    "stk_factor": HistorySpec("stk_factor", "trade_date", "day"),
    "stk_limit": HistorySpec("stk_limit", "trade_date", "day"),
    "index_daily": HistorySpec("index_daily", "trade_date", "day"),
    "index_weekly": HistorySpec("index_weekly", "trade_date", "day"),
    "index_monthly": HistorySpec("index_monthly", "trade_date", "day"),
    "index_dailybasic": HistorySpec("index_dailybasic", "trade_date", "day"),
    "sw_daily": HistorySpec("sw_daily", "trade_date", "day"),
    "ci_daily": HistorySpec("ci_daily", "trade_date", "day"),
    "index_global": HistorySpec("index_global", "trade_date", "day"),
    "fut_daily": HistorySpec("fut_daily", "trade_date", "day"),
    "cb_daily": HistorySpec("cb_daily", "trade_date", "day"),
    "fund_nav": HistorySpec("fund_nav", "end_date", "day"),
    "income": HistorySpec("income", "end_date", "day"),
    "balancesheet": HistorySpec("balancesheet", "end_date", "day"),
    "cashflow": HistorySpec("cashflow", "end_date", "day"),
    "fina_indicator": HistorySpec("fina_indicator", "end_date", "day"),
    "shibor": HistorySpec("shibor", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "lpr_data": HistorySpec("lpr_data", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "hibor": HistorySpec("hibor", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "us_tycr": HistorySpec("us_tycr", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "us_trycr": HistorySpec("us_trycr", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "us_tltr": HistorySpec("us_tltr", "date", "day", ts_code_field=None, req_ts_code_param=None),
    "cn_cpi": HistorySpec(
        "cn_cpi",
        "month",
        "month",
        ts_code_field=None,
        req_start_param="start_m",
        req_end_param="end_m",
        req_ts_code_param=None,
    ),
    "cn_ppi": HistorySpec(
        "cn_ppi",
        "month",
        "month",
        ts_code_field=None,
        req_start_param="start_m",
        req_end_param="end_m",
        req_ts_code_param=None,
    ),
    "cn_m": HistorySpec(
        "cn_m",
        "month",
        "month",
        ts_code_field=None,
        req_start_param="start_m",
        req_end_param="end_m",
        req_ts_code_param=None,
    ),
    "sf_month": HistorySpec(
        "sf_month",
        "month",
        "month",
        ts_code_field=None,
        req_start_param="start_m",
        req_end_param="end_m",
        req_ts_code_param=None,
    ),
    "cn_pmi": HistorySpec(
        "cn_pmi",
        "month",
        "month",
        ts_code_field=None,
        req_start_param="start_m",
        req_end_param="end_m",
        req_ts_code_param=None,
    ),
    "cn_gdp": HistorySpec(
        "cn_gdp",
        "quarter",
        "quarter",
        ts_code_field=None,
        req_start_param="start_q",
        req_end_param="end_q",
        req_ts_code_param=None,
    ),
}


def spec_for(api_name: str) -> HistorySpec | None:
    return SPECS.get(api_name)


def today_key(kind: str) -> str:
    today = _today_date()
    if kind == "day":
        return today.strftime("%Y%m%d")
    if kind == "month":
        return today.strftime("%Y%m")
    if kind == "quarter":
        q = (today.month - 1) // 3 + 1
        return f"{today.year}Q{q}"
    raise ValueError(f"unknown date_kind: {kind}")


def cacheable_end_key(kind: str) -> str:
    """返回可写入历史缓存的最新周期；A 股日线收盘后允许缓存今天。"""

    today = today_key(kind)
    if kind == "day":
        return today if _now_time() >= POST_CLOSE_CACHE_TIME else prev_key(kind, today)
    return prev_key(kind, today)


def prev_key(kind: str, key: str) -> str:
    if kind == "day":
        value = dt.datetime.strptime(key, "%Y%m%d").date() - dt.timedelta(days=1)
        return value.strftime("%Y%m%d")
    if kind == "month":
        year, month = int(key[:4]), int(key[4:]) - 1
        if month == 0:
            year, month = year - 1, 12
        return f"{year:04d}{month:02d}"
    if kind == "quarter":
        year, quarter = int(key[:4]), int(key[-1]) - 1
        if quarter == 0:
            year, quarter = year - 1, 4
        return f"{year}Q{quarter}"
    raise ValueError(f"unknown date_kind: {kind}")


def put_rows(
    database: Path,
    spec: HistorySpec,
    rows: list[dict[str, Any]],
    *,
    ts_code_override: str | None = None,
) -> int:
    """按行缓存历史数据；日线收盘前不缓存今天，避免盘中快照污染历史。"""

    max_cache_key = cacheable_end_key(spec.date_kind)
    records: list[tuple[str, str, str, str]] = []
    for row in rows:
        date_key = row.get(spec.date_field)
        if date_key is None or str(date_key) > max_cache_key:
            continue
        ts_code = "" if spec.ts_code_field is None else str(row.get(spec.ts_code_field) or "")
        records.append(
            (
                spec.api_name,
                ts_code or ts_code_override or "",
                str(date_key),
                json.dumps(row, ensure_ascii=False, default=str),
            )
        )
    if not records:
        return 0

    with _connect(database) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO tushare_history (api_name, ts_code, date_key, data)"
            " VALUES (?, ?, ?, ?)",
            records,
        )
    return len(records)


def query(
    database: Path,
    spec: HistorySpec,
    ts_code: str | None,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    sql = "SELECT data FROM tushare_history WHERE api_name=?"
    args: list[Any] = [spec.api_name]
    if spec.ts_code_field is not None:
        sql += " AND ts_code=?"
        args.append(ts_code or "")
    if start:
        sql += " AND date_key>=?"
        args.append(start)
    if end:
        sql += " AND date_key<=?"
        args.append(end)
    sql += " ORDER BY date_key DESC"
    with _connect(database) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(row[0]) for row in rows]


def missing_segments(
    database: Path,
    spec: HistorySpec,
    ts_code: str | None,
    start: str | None,
    end: str | None,
) -> list[tuple[str | None, str | None]]:
    max_cache_key = cacheable_end_key(spec.date_kind)
    end_clamped = max_cache_key if end is None or end > max_cache_key else end
    if start is not None and end_clamped is not None and start > end_clamped:
        return []

    local_min, local_max = _coverage(database, spec, ts_code)
    if local_min is None or local_max is None:
        return [(start, end_clamped)]

    gaps: list[tuple[str | None, str | None]] = []
    if start is None or start < local_min:
        gaps.append((start, prev_key(spec.date_kind, local_min)))
    if end_clamped is None or end_clamped > local_max:
        gaps.append((_next_key(spec.date_kind, local_max), end_clamped))
    return gaps


def clear(database: Path, api_name: str | None = None) -> int:
    with _connect(database) as conn:
        if api_name:
            cur = conn.execute("DELETE FROM tushare_history WHERE api_name=?", (api_name,))
        else:
            cur = conn.execute("DELETE FROM tushare_history")
        return cur.rowcount


def _coverage(
    database: Path,
    spec: HistorySpec,
    ts_code: str | None,
) -> tuple[str | None, str | None]:
    sql = "SELECT MIN(date_key), MAX(date_key) FROM tushare_history WHERE api_name=?"
    args: list[Any] = [spec.api_name]
    if spec.ts_code_field is not None:
        sql += " AND ts_code=?"
        args.append(ts_code or "")
    with _connect(database) as conn:
        row = conn.execute(sql, args).fetchone()
    if not row or row[0] is None:
        return None, None
    return row[0], row[1]


def _next_key(kind: str, key: str) -> str:
    if kind == "day":
        value = dt.datetime.strptime(key, "%Y%m%d").date() + dt.timedelta(days=1)
        return value.strftime("%Y%m%d")
    if kind == "month":
        year, month = int(key[:4]), int(key[4:]) + 1
        if month == 13:
            year, month = year + 1, 1
        return f"{year:04d}{month:02d}"
    if kind == "quarter":
        year, quarter = int(key[:4]), int(key[-1]) + 1
        if quarter == 5:
            year, quarter = year + 1, 1
        return f"{year}Q{quarter}"
    raise ValueError(f"unknown date_kind: {kind}")


def _today_date() -> dt.date:
    return dt.date.today()


def _now_time() -> dt.time:
    return dt.datetime.now().time()


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=SQLITE_TIMEOUT_SECONDS)
    configure_sqlite_connection(conn)
    migrate_market_db(conn)
    return conn
