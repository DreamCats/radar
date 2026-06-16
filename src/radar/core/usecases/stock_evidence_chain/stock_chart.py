from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.market.quotes import RealtimeQuote, get_public_realtime_quote
from radar.core.tushare import client as tushare_client
from radar.core.tushare import history
from radar.core.tushare.exceptions import TushareError
from radar.core.tushare.realtime import RealtimeDailyQuote, get_realtime_daily_quote

INTRADAY_START_TIME = dt.time(9, 30)


class StockEvidenceStockCandle(BaseModel):
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


class StockEvidenceStockChart(BaseModel):
    ts_code: str
    candles: list[StockEvidenceStockCandle] = Field(default_factory=list)
    latest_trade_date: str | None = None
    latest_source: str | None = None
    latest_is_realtime: bool = False
    missing_reason: str | None = None


def get_stock_evidence_stock_chart(
    config: RadarConfig,
    *,
    ts_code: str,
    days: int = 120,
    refresh: bool = False,
) -> StockEvidenceStockChart:
    code = ts_code.strip().upper()
    if not code:
        raise ValueError("ts_code 不能为空")

    spec = history.spec_for("daily")
    if spec is None:
        raise ValueError("daily 行情缓存规格不存在")

    if refresh:
        _refresh_recent_daily_cache(config, code, days=days)
    raw_rows = history.query(config.market_database_path, spec, code, start=None, end=None)
    candles = [_candle(row) for row in raw_rows]
    candles = [item for item in candles if item is not None]
    candles.sort(key=lambda item: item.trade_date)
    latest_realtime_source = _append_intraday_candle(config, code, candles) if refresh else None
    limited = candles[-days:]

    return StockEvidenceStockChart(
        ts_code=code,
        candles=limited,
        latest_trade_date=limited[-1].trade_date if limited else None,
        latest_source=_latest_source(limited, latest_realtime_source),
        latest_is_realtime=(
            bool(latest_realtime_source)
            and bool(limited)
            and limited[-1].trade_date == history.today_key("day")
        ),
        missing_reason=None if limited else "本地 market.sqlite3 暂无该股票日线缓存",
    )


def _refresh_recent_daily_cache(config: RadarConfig, ts_code: str, *, days: int) -> None:
    spec = history.spec_for("daily")
    if spec is None:
        return
    latest_cache_key = history.cacheable_end_key(spec.date_kind)
    raw_rows = history.query(config.market_database_path, spec, ts_code, start=None, end=None)
    latest_local = max((str(row.get("trade_date") or "") for row in raw_rows), default="")
    if latest_local >= latest_cache_key:
        return

    start = _next_day(latest_local) if latest_local else _lookback_start(days)
    try:
        tushare_client.call(
            config,
            "daily",
            {"ts_code": ts_code, "start_date": start, "end_date": latest_cache_key},
            use_cache=True,
        )
    except TushareError:
        # K 线抽屉优先展示本地缓存；Tushare 失败时不中断页面。
        return


def _append_intraday_candle(
    config: RadarConfig,
    ts_code: str,
    candles: list[StockEvidenceStockCandle],
) -> str | None:
    today_key = history.today_key("day")
    if not _should_use_realtime_quote(config, today_key):
        return None
    source = "rt_k"
    try:
        quote = get_realtime_daily_quote(config, ts_code=ts_code, use_cache=True)
    except TushareError:
        quote = None
    candle = _realtime_candle(quote, today_key)
    if candle is None:
        public_quote = get_public_realtime_quote(config, ts_code=ts_code)
        candle = _public_realtime_candle(public_quote, today_key)
        source = f"{public_quote.source}_rt" if public_quote is not None else source
    if candle is None:
        return None
    if candles and candles[-1].trade_date == today_key:
        candles[-1] = candle
    else:
        candles.append(candle)
    return source


def _should_use_realtime_quote(config: RadarConfig, today_key: str) -> bool:
    now = _now_time()
    if now < INTRADAY_START_TIME or now >= history.POST_CLOSE_CACHE_TIME:
        return False
    return _is_trading_day(config, today_key)


def _is_trading_day(config: RadarConfig, trade_date: str) -> bool:
    try:
        rows = tushare_client.call(
            config,
            "trade_cal",
            {"exchange": "", "start_date": trade_date, "end_date": trade_date},
            fields="cal_date,is_open",
            use_cache=True,
        )
    except TushareError:
        return False
    return any(
        str(row.get("cal_date")) == trade_date
        and str(row.get("is_open")) in {"1", "1.0", "True", "true"}
        for row in rows
    )


def _realtime_candle(
    quote: RealtimeDailyQuote | None,
    trade_date: str,
) -> StockEvidenceStockCandle | None:
    if quote is None or quote.open is None or quote.close is None:
        return None
    high = quote.high if quote.high is not None else max(quote.open, quote.close)
    low = quote.low if quote.low is not None else min(quote.open, quote.close)
    change = quote.close - quote.pre_close if quote.pre_close else None
    return StockEvidenceStockCandle(
        trade_date=trade_date,
        open=quote.open,
        high=high,
        low=low,
        close=quote.close,
        pre_close=quote.pre_close,
        change=change,
        pct_chg=_pct_change(change, quote.pre_close),
        vol=quote.vol,
        amount=quote.amount,
    )


def _public_realtime_candle(
    quote: RealtimeQuote | None,
    trade_date: str,
) -> StockEvidenceStockCandle | None:
    if quote is None or quote.open is None or quote.close is None:
        return None
    high = quote.high if quote.high is not None else max(quote.open, quote.close)
    low = quote.low if quote.low is not None else min(quote.open, quote.close)
    change = quote.close - quote.pre_close if quote.pre_close else None
    return StockEvidenceStockCandle(
        trade_date=trade_date,
        open=quote.open,
        high=high,
        low=low,
        close=quote.close,
        pre_close=quote.pre_close,
        change=change,
        pct_chg=_pct_change(change, quote.pre_close),
        vol=quote.volume_shares / 100 if quote.volume_shares is not None else None,
        amount=quote.amount_yuan / 1000 if quote.amount_yuan is not None else None,
    )


def _latest_source(
    candles: list[StockEvidenceStockCandle],
    latest_realtime_source: str | None,
) -> str | None:
    if not candles:
        return None
    if latest_realtime_source and candles[-1].trade_date == history.today_key("day"):
        return latest_realtime_source
    return "daily"


def _now_time() -> dt.time:
    return dt.datetime.now().time()


def _next_day(value: str) -> str:
    return (dt.datetime.strptime(value, "%Y%m%d").date() + dt.timedelta(days=1)).strftime("%Y%m%d")


def _lookback_start(days: int) -> str:
    lookback_days = max(days * 2, 180)
    return (dt.date.today() - dt.timedelta(days=lookback_days)).strftime("%Y%m%d")


def _candle(row: dict[str, Any]) -> StockEvidenceStockCandle | None:
    trade_date = str(row.get("trade_date") or "")
    open_price = _float(row.get("open"))
    high = _float(row.get("high"))
    low = _float(row.get("low"))
    close = _float(row.get("close"))
    if not trade_date or open_price is None or high is None or low is None or close is None:
        return None
    return StockEvidenceStockCandle(
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


def _pct_change(change: float | None, pre_close: float | None) -> float | None:
    return change / pre_close * 100 if change is not None and pre_close else None
