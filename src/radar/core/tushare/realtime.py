from __future__ import annotations

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.tushare.client import call

RT_K_FIELDS = "ts_code,name,pre_close,open,high,low,close,vol,amount,num"


class RealtimeDailyQuote(BaseModel):
    ts_code: str
    name: str | None = None
    pre_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    vol: float | None = None
    amount: float | None = None
    num: int | None = None


def get_realtime_daily_quote(
    config: RadarConfig,
    *,
    ts_code: str,
    use_cache: bool = True,
) -> RealtimeDailyQuote | None:
    """查询 Tushare 实时日线快照；盘中数据只走短期 KV 缓存，不写历史行缓存。"""

    code = ts_code.strip().upper()
    if not code:
        raise ValueError("ts_code 不能为空")

    rows = call(
        config,
        "rt_k",
        {"ts_code": code},
        fields=RT_K_FIELDS,
        use_cache=use_cache,
    )
    if not rows:
        return None
    return _quote(rows[0], fallback_ts_code=code)


def _quote(row: dict[str, object], *, fallback_ts_code: str) -> RealtimeDailyQuote:
    return RealtimeDailyQuote(
        ts_code=str(row.get("ts_code") or fallback_ts_code),
        name=str(row["name"]) if row.get("name") else None,
        pre_close=_float(row.get("pre_close")),
        open=_float(row.get("open")),
        high=_float(row.get("high")),
        low=_float(row.get("low")),
        close=_float(row.get("close")),
        vol=_float(row.get("vol")),
        amount=_float(row.get("amount")),
        num=_int(row.get("num")),
    )


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
