from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.tushare import history


class StrategyStockCandle(BaseModel):
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None = None
    change: float | None = None
    pct_chg: float | None = None
    vol: float | None = None
    amount: float | None = None


class StrategyStockChart(BaseModel):
    ts_code: str
    candles: list[StrategyStockCandle] = Field(default_factory=list)
    latest_trade_date: str | None = None
    missing_reason: str | None = None


def get_strategy_stock_chart(
    config: RadarConfig,
    *,
    ts_code: str,
    days: int = 120,
) -> StrategyStockChart:
    code = ts_code.strip().upper()
    if not code:
        raise ValueError("ts_code 不能为空")

    spec = history.spec_for("daily")
    if spec is None:
        raise ValueError("daily 行情缓存规格不存在")

    raw_rows = history.query(config.market_database_path, spec, code, start=None, end=None)
    candles = [_candle(row) for row in raw_rows]
    candles = [item for item in candles if item is not None]
    candles.sort(key=lambda item: item.trade_date)
    limited = candles[-days:]

    return StrategyStockChart(
        ts_code=code,
        candles=limited,
        latest_trade_date=limited[-1].trade_date if limited else None,
        missing_reason=None if limited else "本地 market.sqlite3 暂无该股票日线缓存",
    )


def _candle(row: dict[str, Any]) -> StrategyStockCandle | None:
    trade_date = str(row.get("trade_date") or "")
    open_price = _float(row.get("open"))
    high = _float(row.get("high"))
    low = _float(row.get("low"))
    close = _float(row.get("close"))
    if not trade_date or open_price is None or high is None or low is None or close is None:
        return None
    return StrategyStockCandle(
        trade_date=trade_date,
        open=open_price,
        high=high,
        low=low,
        close=close,
        pre_close=_float(row.get("pre_close")),
        change=_float(row.get("change")),
        pct_chg=_float(row.get("pct_chg")),
        vol=_float(row.get("vol")),
        amount=_float(row.get("amount")),
    )


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
