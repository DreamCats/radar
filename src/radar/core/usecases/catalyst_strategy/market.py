from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from radar.core.config import RadarConfig
from radar.core.market.quotes import get_public_realtime_quote
from radar.core.tushare import TushareError
from radar.core.tushare.client import call as tushare_call
from radar.core.usecases.catalyst_strategy.models import (
    CatalystStockContext,
    FinancialTrendPoint,
    MarketSnapshot,
)

DAILY_BASIC_FIELDS = "ts_code,trade_date,close,pe,pe_ttm,total_share,total_mv,circ_mv"
INCOME_FIELDS = "ts_code,end_date,ann_date,total_revenue,revenue,n_income_attr_p,n_income"


def load_market_snapshot(
    config: RadarConfig,
    context: CatalystStockContext,
    *,
    today: date | None = None,
) -> MarketSnapshot:
    if not context.ts_code:
        return MarketSnapshot(stock_name=context.stock_name, valuation_basis="missing", error="缺少 ts_code")

    snapshot = MarketSnapshot(ts_code=context.ts_code, stock_name=context.stock_name)
    quote = get_public_realtime_quote(config, ts_code=context.ts_code)
    if quote is not None and quote.close is not None:
        snapshot.realtime_price = quote.close
        snapshot.realtime_at = quote.timestamp
        snapshot.realtime_source = quote.source
        snapshot.price_basis = "realtime"

    try:
        daily_rows = _daily_basic_rows(config, context.ts_code, today=today)
    except TushareError as error:
        snapshot.error = str(error)[:300]
        if snapshot.price_basis == "unknown":
            snapshot.price_basis = "realtime" if snapshot.realtime_price is not None else "missing"
        daily_rows = []

    latest = _latest_daily_basic(daily_rows)
    if latest is None:
        if snapshot.error is None:
            snapshot.error = "未查到 daily_basic"
        if snapshot.price_basis == "unknown":
            snapshot.price_basis = "realtime" if snapshot.realtime_price is not None else "missing"
    else:
        snapshot.last_trade_date = _optional_str(latest.get("trade_date"))
        snapshot.last_close = _float(latest.get("close"))
        snapshot.total_share_10000 = _float(latest.get("total_share"))
        snapshot.total_mv_yi = _wan_yuan_to_yi(latest.get("total_mv"))
        snapshot.circ_mv_yi = _wan_yuan_to_yi(latest.get("circ_mv"))
        snapshot.pe = _float(latest.get("pe"))
        snapshot.pe_ttm = _float(latest.get("pe_ttm"))
        if snapshot.price_basis == "unknown" and snapshot.last_close is not None:
            snapshot.price_basis = "last_close"

        price = snapshot.realtime_price or snapshot.last_close
        if price is not None and snapshot.total_share_10000 is not None:
            snapshot.estimated_total_mv_yi = snapshot.total_share_10000 * price / 10_000
        elif snapshot.total_mv_yi is not None:
            snapshot.estimated_total_mv_yi = snapshot.total_mv_yi

        if snapshot.realtime_price and snapshot.last_close:
            ratio = snapshot.realtime_price / snapshot.last_close
            if snapshot.pe is not None:
                snapshot.estimated_pe = snapshot.pe * ratio
            if snapshot.pe_ttm is not None:
                snapshot.estimated_pe_ttm = snapshot.pe_ttm * ratio
            snapshot.valuation_basis = "realtime_estimated"
        elif snapshot.total_mv_yi is not None or snapshot.pe_ttm is not None:
            snapshot.valuation_basis = "last_close"
        _apply_pe_percentiles(snapshot, daily_rows)

    _apply_implied_profit(snapshot)
    _apply_financial_trend(config, context.ts_code, snapshot, today=today)
    return snapshot


def _daily_basic_rows(
    config: RadarConfig,
    ts_code: str,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    end = today or date.today()
    start = end - timedelta(days=420)
    return tushare_call(
        config,
        "daily_basic",
        {
            "ts_code": ts_code,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        },
        fields=DAILY_BASIC_FIELDS,
    )


def _latest_daily_basic(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: str(row.get("trade_date") or ""))


def _apply_pe_percentiles(snapshot: MarketSnapshot, rows: list[dict[str, Any]]) -> None:
    sorted_rows = sorted(rows, key=lambda row: str(row.get("trade_date") or ""), reverse=True)
    current = snapshot.estimated_pe_ttm or snapshot.pe_ttm
    snapshot.pe_ttm_percentile_60d = _pe_percentile(sorted_rows, current, 60)
    snapshot.pe_ttm_percentile_120d = _pe_percentile(sorted_rows, current, 120)
    snapshot.pe_ttm_percentile_250d = _pe_percentile(sorted_rows, current, 250)


def _pe_percentile(rows: list[dict[str, Any]], current: float | None, window: int) -> float | None:
    if current is None or current <= 0:
        return None
    values = [_float(row.get("pe_ttm")) for row in rows[:window]]
    values = [value for value in values if value is not None and value > 0]
    if not values:
        return None
    return sum(1 for value in values if value <= current) * 100 / len(values)


def _apply_implied_profit(snapshot: MarketSnapshot) -> None:
    market_cap = snapshot.estimated_total_mv_yi or snapshot.total_mv_yi
    pe_ttm = snapshot.estimated_pe_ttm or snapshot.pe_ttm
    if market_cap is not None and pe_ttm is not None and pe_ttm > 0:
        snapshot.implied_net_profit_ttm_yi = market_cap / pe_ttm


def _apply_financial_trend(
    config: RadarConfig,
    ts_code: str,
    snapshot: MarketSnapshot,
    *,
    today: date | None = None,
) -> None:
    try:
        rows = _income_rows(config, ts_code, today=today)
    except TushareError as error:
        snapshot.financial_error = str(error)[:300]
        return

    trend = _annual_financial_trend(rows)
    snapshot.financial_trend = trend
    if trend:
        latest = trend[0]
        snapshot.latest_financial_period = latest.period
        snapshot.latest_revenue_yi = latest.revenue_yi
        snapshot.latest_net_profit_yi = latest.net_profit_yi


def _income_rows(
    config: RadarConfig,
    ts_code: str,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    end = today or date.today()
    start = end - timedelta(days=365 * 5)
    return tushare_call(
        config,
        "income",
        {
            "ts_code": ts_code,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        },
        fields=INCOME_FIELDS,
    )


def _annual_financial_trend(rows: list[dict[str, Any]]) -> list[FinancialTrendPoint]:
    by_period: dict[str, dict[str, Any]] = {}
    for row in rows:
        period = _optional_str(row.get("end_date"))
        if not period or not period.endswith("1231"):
            continue
        previous = by_period.get(period)
        if previous is None or str(row.get("ann_date") or "") > str(previous.get("ann_date") or ""):
            by_period[period] = row

    trend: list[FinancialTrendPoint] = []
    for period, row in sorted(by_period.items(), reverse=True)[:3]:
        trend.append(
            FinancialTrendPoint(
                period=period,
                revenue_yi=_first_present(
                    _yuan_to_yi(row.get("total_revenue")),
                    _yuan_to_yi(row.get("revenue")),
                ),
                net_profit_yi=_first_present(
                    _yuan_to_yi(row.get("n_income_attr_p")),
                    _yuan_to_yi(row.get("n_income")),
                ),
            )
        )
    return trend


def _wan_yuan_to_yi(value: object) -> float | None:
    amount = _float(value)
    return None if amount is None else amount / 10_000


def _yuan_to_yi(value: object) -> float | None:
    amount = _float(value)
    return None if amount is None else amount / 100_000_000


def _first_present(*values: float | None) -> float | None:
    return next((value for value in values if value is not None), None)


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
