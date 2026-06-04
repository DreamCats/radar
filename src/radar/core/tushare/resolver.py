from __future__ import annotations

import re
from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare.client import call
from radar.core.tushare.exceptions import TushareApiError


_TS_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"^\d{6}$")


def resolve_stock(config: RadarConfig, value: str) -> str:
    """把 ts_code、6 位代码或中文名解析成唯一 ts_code。"""

    if _TS_CODE_RE.match(value):
        return value.upper()

    candidates = _stock_candidates(_all_stocks(config), value)
    if len(candidates) == 1:
        return str(candidates[0]["ts_code"])
    if not candidates:
        raise TushareApiError(f"找不到股票 {value!r}")

    listed = ", ".join(f"{row['ts_code']}({row.get('name', '')})" for row in candidates[:5])
    raise TushareApiError(f"股票 {value!r} 匹配到多个，请用 ts_code 指定: {listed}")


def _stock_candidates(rows: tuple[dict[str, Any], ...], value: str) -> list[dict[str, Any]]:
    candidates = [row for row in rows if row.get("name") == value]
    if not candidates and _SYMBOL_RE.match(value):
        candidates = [row for row in rows if row.get("symbol") == value]
    return candidates


def _all_stocks(config: RadarConfig) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for status in ("L", "D", "P"):
        rows.extend(
            call(
                config,
                "stock_basic",
                params={"list_status": status},
                fields="ts_code,symbol,name",
            )
        )
    return tuple(rows)
